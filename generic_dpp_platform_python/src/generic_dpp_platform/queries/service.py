"""Predicate query execution over materialized facts or current payloads."""

from __future__ import annotations

import inspect
from collections import OrderedDict
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Any, Protocol

from .helpers import is_numeric, matches_filter, matches_value, resolve_path, select_fields
from .index import FACT_COLLECTION
from .models import (
    PredicateQueryRequest,
    PredicateQueryResponse,
    QueryExecutionMode,
    QueryResultMode,
)


class FactRepository(Protocol):
    def find_all_by_subject_type(self, subject_type: str) -> Any: ...


class MongoFactRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def find_all_by_subject_type(self, subject_type: str) -> list[dict[str, Any]]:
        return await self._db[FACT_COLLECTION].find(
            {"subject_type": subject_type}, {"_id": 0}
        ).to_list(None)


class IndexedQueryMatcher:
    """Match a subject type's materialized fact groups.

    The repository seam keeps the data-independent matcher easy to unit test.
    """

    def __init__(self, repository: FactRepository) -> None:
        self._repository = repository

    async def matching_fact_groups(self, request: PredicateQueryRequest) -> list[dict[str, dict[str, Any]]]:
        facts = self._repository.find_all_by_subject_type(request.subject_type)
        if inspect.isawaitable(facts):
            facts = await facts
        grouped: OrderedDict[str, dict[str, dict[str, Any]]] = OrderedDict()
        for fact in facts:
            grouped.setdefault(fact["logical_dpp_id"], OrderedDict())[fact["path"]] = fact
        return [
            facts_by_path
            for facts_by_path in grouped.values()
            if _facts_match_request(facts_by_path, request)
        ]

    async def select(self, request: PredicateQueryRequest) -> list[dict[str, Any]]:
        return [_select_indexed_fields(group, request.return_fields) for group in await self.matching_fact_groups(request)]

    async def count(self, request: PredicateQueryRequest) -> int:
        return len(await self.matching_fact_groups(request))

    async def sum(self, request: PredicateQueryRequest) -> float:
        total = 0.0
        for group in await self.matching_fact_groups(request):
            fact = group.get(request.aggregate_path or "")
            if fact is None:
                continue
            if fact.get("value_number") is None:
                raise ValueError(f"Aggregate value is not numeric for path: {request.aggregate_path}")
            total += float(fact["value_number"])
        return total


class OnDemandQueryMatcher:
    """Pure matcher for current revision payloads."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def matching_documents(self, request: PredicateQueryRequest) -> list[dict[str, Any]]:
        return [
            document
            for document in self._documents
            if not request.filters or all(matches_filter(document, filter_) for filter_ in request.filters)
        ]

    def select(self, request: PredicateQueryRequest) -> list[dict[str, Any]]:
        return [select_fields(document, request.return_fields) for document in self.matching_documents(request)]

    def count(self, request: PredicateQueryRequest) -> int:
        return len(self.matching_documents(request))

    def sum(self, request: PredicateQueryRequest) -> float:
        total = 0.0
        for document in self.matching_documents(request):
            value = resolve_path(document, request.aggregate_path)
            if value is None:
                continue
            if not is_numeric(value):
                raise ValueError(f"Aggregate value is not numeric: {value}")
            total += float(value)
        return total


async def query_predicate(
    db: AsyncIOMotorDatabase,
    request: PredicateQueryRequest,
) -> PredicateQueryResponse:
    """Execute a validated platform-local query with Java-compatible results."""
    validate_request(request)
    platform_config = await db.platform_config.find_one({}, {"_id": 0})
    platform_id = (platform_config or {}).get("issuer_id", "")

    if not await db.subject_types.find_one({"name": request.subject_type}):
        return empty_response(request, platform_id)

    if request.execution_mode is QueryExecutionMode.INDEXED:
        matcher: IndexedQueryMatcher | OnDemandQueryMatcher = IndexedQueryMatcher(MongoFactRepository(db))
    else:
        matcher = OnDemandQueryMatcher(await _current_payloads_for_subject_type(db, request.subject_type))

    if request.result_mode is QueryResultMode.SELECT:
        return PredicateQueryResponse(
            result_mode=request.result_mode,
            execution_mode=request.execution_mode,
            platform_id=platform_id,
            matches=await matcher.select(request) if isinstance(matcher, IndexedQueryMatcher) else matcher.select(request),
        )
    if request.result_mode is QueryResultMode.COUNT:
        return PredicateQueryResponse(
            result_mode=request.result_mode,
            execution_mode=request.execution_mode,
            platform_id=platform_id,
            count=await matcher.count(request) if isinstance(matcher, IndexedQueryMatcher) else matcher.count(request),
        )
    return PredicateQueryResponse(
        result_mode=request.result_mode,
        execution_mode=request.execution_mode,
        platform_id=platform_id,
        aggregate=await matcher.sum(request) if isinstance(matcher, IndexedQueryMatcher) else matcher.sum(request),
    )


def validate_request(request: PredicateQueryRequest) -> None:
    """Apply the Java service's request-level validation rules."""
    if not request.subject_type or not request.subject_type.strip():
        raise ValueError("subject_type is required")
    if request.result_mode is QueryResultMode.SUM:
        if request.aggregate_path is None or not request.aggregate_path.strip():
            raise ValueError("aggregate_path is required for SUM queries")
    elif request.aggregate_path is not None and request.aggregate_path.strip():
        raise ValueError("aggregate_path is only supported for SUM queries")


def empty_response(request: PredicateQueryRequest, platform_id: str) -> PredicateQueryResponse:
    if request.result_mode is QueryResultMode.SELECT:
        return PredicateQueryResponse(
            result_mode=request.result_mode,
            execution_mode=request.execution_mode,
            platform_id=platform_id,
            matches=[],
        )
    if request.result_mode is QueryResultMode.COUNT:
        return PredicateQueryResponse(
            result_mode=request.result_mode,
            execution_mode=request.execution_mode,
            platform_id=platform_id,
            count=0,
        )
    return PredicateQueryResponse(
        result_mode=request.result_mode,
        execution_mode=request.execution_mode,
        platform_id=platform_id,
        aggregate=0.0,
    )


async def _current_payloads_for_subject_type(
    db: AsyncIOMotorDatabase,
    subject_type: str,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    async for logical_dpp in db.logical_dpps.find({"subject_type": subject_type}, {"_id": 0}):
        revision = await db.dpp_revisions.find_one(
            {
                "dpp_id": logical_dpp["dpp_id"],
                "dpp_version": logical_dpp["current_version"],
            },
            {"_id": 0, "dpp_document": 1},
        )
        if revision is not None:
            payloads.append(revision["dpp_document"])
    return payloads


def _facts_match_request(facts_by_path: dict[str, dict[str, Any]], request: PredicateQueryRequest) -> bool:
    return not request.filters or all(
        matches_value(_fact_value(facts_by_path.get(filter_.path)), filter_)
        for filter_ in request.filters
    )


def _fact_value(fact: dict[str, Any] | None) -> Any | None:
    if fact is None:
        return None
    for field in ("value_text", "value_number", "value_boolean"):
        if fact.get(field) is not None:
            return fact[field]
    return None


def _select_indexed_fields(
    facts_by_path: dict[str, dict[str, Any]],
    return_fields: list[str] | None,
) -> dict[str, Any]:
    if not return_fields:
        return {path: _fact_value(fact) for path, fact in facts_by_path.items()}
    return {
        path: _fact_value(facts_by_path[path])
        for path in return_fields
        if path in facts_by_path
    }
