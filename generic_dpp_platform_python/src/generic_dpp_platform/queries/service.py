"""Platform-local derived query execution over current revisions."""

from __future__ import annotations

import inspect
from collections import OrderedDict
from motor.motor_asyncio import AsyncIOMotorDatabase
from numbers import Number
from typing import Any, Protocol

from .helpers import is_numeric, matches_filter, matches_value, resolve_path, select_fields
from .index import FACT_COLLECTION, REFERENCE_COLLECTION
from .models import (
    PredicateQueryRequest,
    PredicateQueryResponse,
    QueryExecutionMode,
    QueryResultMode,
    TraverseQueryRequest,
    TraverseQueryResponse,
    TraverseSourceScope,
)


class FactRepository(Protocol):
    def find_all_by_subject_type(self, subject_type: str) -> Any: ...


class MongoFactRepository:
    """Reads the materialized attribute facts for indexed predicate retrieval."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def find_all_by_subject_type(self, subject_type: str) -> list[dict[str, Any]]:
        """Return the current attribute facts for one local subject type."""
        return await self._db[FACT_COLLECTION].find(
            {"subject_type": subject_type}, {"_id": 0}
        ).to_list(None)


class IndexedQueryMatcher:
    """Evaluate predicate retrieval from materialized attribute facts.

    Facts are the local indexed representation of the derived query view for
    current revisions. Indexing changes execution cost, not query semantics.
    """

    def __init__(self, repository: FactRepository) -> None:
        self._repository = repository

    async def matching_fact_groups(self, request: PredicateQueryRequest) -> list[dict[str, dict[str, Any]]]:
        """Return current local fact groups that satisfy every predicate."""
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
        """Project requested attribute facts from each matching local group."""
        return [_select_indexed_fields(group, request.return_fields) for group in await self.matching_fact_groups(request)]

    async def count(self, request: PredicateQueryRequest) -> int:
        """Count local fact groups that satisfy every predicate."""
        return len(await self.matching_fact_groups(request))

    async def sum(self, request: PredicateQueryRequest) -> float:
        """Sum the requested numeric attribute fact over matching local groups."""
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
    """Evaluate predicate retrieval by scanning current revision payloads."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def matching_documents(self, request: PredicateQueryRequest) -> list[dict[str, Any]]:
        """Return current local payloads that satisfy every predicate."""
        return [
            document
            for document in self._documents
            if not request.filters or all(matches_filter(document, filter_) for filter_ in request.filters)
        ]

    def select(self, request: PredicateQueryRequest) -> list[dict[str, Any]]:
        """Project requested payload fields from each matching document."""
        return [select_fields(document, request.return_fields) for document in self.matching_documents(request)]

    def count(self, request: PredicateQueryRequest) -> int:
        """Count current local payloads that satisfy every predicate."""
        return len(self.matching_documents(request))

    def sum(self, request: PredicateQueryRequest) -> float:
        """Sum a numeric payload path over matching current local payloads."""
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
    """Validate and execute platform-local predicate retrieval.

    Selects the indexed or on-demand matcher and returns a local SELECT, COUNT,
    or SUM response. Federation fan-out and merging are external concerns.
    """
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


async def query_traverse(
    db: AsyncIOMotorDatabase,
    request: TraverseQueryRequest,
) -> TraverseQueryResponse:
    """Validate and execute platform-local reverse traversal.

    Traversal searches current source revisions in the caller-supplied scope
    for references to a logical DPP or exact revision. The workload or another
    federation client owns resolver routing and cross-platform fan-out.
    """
    validate_traverse_request(request)
    platform_config = await db.platform_config.find_one({}, {"_id": 0})
    platform_id = (platform_config or {}).get("issuer_id", "")

    if request.execution_mode is QueryExecutionMode.INDEXED:
        matches = await _indexed_traverse_matches(db, request)
    else:
        matches = await _on_demand_traverse_matches(db, request)

    return TraverseQueryResponse(
        platform_id=platform_id,
        subject_type=request.subject_type,
        dpp_id=request.dpp_id,
        matches=matches,
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


def validate_traverse_request(request: TraverseQueryRequest) -> None:
    """Apply the Java DTO and service validation rules for traversal."""
    if not request.dpp_id or not request.dpp_id.strip():
        raise ValueError("dpp_id is required")
    if not request.subject_type or not request.subject_type.strip():
        raise ValueError("subject_type is required")
    # ``sources`` is a required, but intentionally allowed-to-be-empty, list
    # in the Java DTO.  The per-source type is a Java ``@NotBlank`` field.
    for index, source in enumerate(request.sources):
        if not source.subject_type or not source.subject_type.strip():
            raise ValueError(f"sources[{index}].subject_type is required")


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


async def _indexed_traverse_matches(
    db: AsyncIOMotorDatabase,
    request: TraverseQueryRequest,
) -> list[dict[str, Any]]:
    """Use the current reference materialization, then Java-style fact output."""
    matches: list[dict[str, Any]] = []
    for source_scope in request.sources:
        query: dict[str, Any] = {
            "target_subject_type": request.subject_type,
            "target_dpp_id": request.dpp_id,
            "source_subject_type": source_scope.subject_type,
        }
        if request.revision_number is not None:
            # A materialized reference with a revision is always HARD, exactly
            # as the Java extractor classifies it.
            query["target_revision_number"] = request.revision_number
            query["reference_type"] = "HARD"

        source_ids: list[str] = []
        seen_source_ids: set[str] = set()
        async for reference in db[REFERENCE_COLLECTION].find(query, {"_id": 0}):
            if not _reference_path_in_scope(reference["reference_path"], source_scope):
                continue
            source_id = reference["source_logical_dpp_id"]
            if source_id not in seen_source_ids:
                seen_source_ids.add(source_id)
                source_ids.append(source_id)

        for source_id in source_ids:
            facts = await db[FACT_COLLECTION].find(
                {"logical_dpp_id": source_id}, {"_id": 0}
            ).to_list(None)
            if facts:
                facts_by_path = OrderedDict((fact["path"], fact) for fact in facts)
                matches.append(_select_indexed_fields(facts_by_path, None))
    return matches


async def _on_demand_traverse_matches(
    db: AsyncIOMotorDatabase,
    request: TraverseQueryRequest,
) -> list[dict[str, Any]]:
    """Load current source payloads and inspect ``$ref`` objects at query time."""
    matches: list[dict[str, Any]] = []
    for source_scope in request.sources:
        for document in await _current_payloads_for_subject_type(db, source_scope.subject_type):
            if _document_contains_matching_reference(document, source_scope, request):
                matches.append(document)
    return matches


def _reference_path_in_scope(reference_path: str, source_scope: TraverseSourceScope) -> bool:
    if not source_scope.reference_paths:
        return True
    for path in source_scope.reference_paths:
        # Java first checks ``path`` / ``path.$ref``.  The prefix case extends
        # that same payload-path intent to list elements, whose extractor path
        # includes an index such as ``modules[0]``.
        if reference_path == path or reference_path.startswith(f"{path}["):
            return True
    return False


def _document_contains_matching_reference(
    document: dict[str, Any],
    source_scope: TraverseSourceScope,
    request: TraverseQueryRequest,
) -> bool:
    if not source_scope.reference_paths:
        return _contains_matching_reference(document, request)
    return any(
        _contains_matching_reference(resolve_path(document, path), request)
        for path in source_scope.reference_paths
    )


def _contains_matching_reference(value: Any, request: TraverseQueryRequest) -> bool:
    if isinstance(value, dict):
        if "$ref" in value and _reference_matches(value, request):
            return True
        return any(_contains_matching_reference(child, request) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_matching_reference(child, request) for child in value)
    return False


def _reference_matches(reference_object: dict[str, Any], request: TraverseQueryRequest) -> bool:
    raw_reference = reference_object.get("$ref")
    if not isinstance(raw_reference, str):
        return False
    parts = raw_reference.split("/")
    if len(parts) < 2 or len(parts) > 3:
        return False
    if parts[0] != request.subject_type or parts[1] != request.dpp_id:
        return False

    revision: int | None = None
    if len(parts) == 3:
        try:
            revision = int(parts[2])
        except ValueError:
            return False
    elif isinstance(reference_object.get("version"), Number) and not isinstance(reference_object.get("version"), bool):
        revision = int(reference_object["version"])
    return request.revision_number is None or request.revision_number == revision


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
