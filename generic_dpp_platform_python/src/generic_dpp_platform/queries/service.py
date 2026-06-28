"""Platform-local derived query execution over current revisions."""

from __future__ import annotations

import inspect
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from motor.motor_asyncio import AsyncIOMotorDatabase
from numbers import Number
from typing import Any, Protocol

from .helpers import is_numeric, matches_filter, matches_value, resolve_path, select_fields
from .index import FACT_COLLECTION, REFERENCE_COLLECTION
from .models import (
    PredicateFilter,
    PredicateOperator,
    PredicateQueryRequest,
    PredicateQueryResponse,
    QueryExecutionMode,
    QueryResultMode,
    TraverseQueryRequest,
    TraverseQueryResponse,
    TraverseSourceScope,
)


class FactRepository(Protocol):
    def find_by_request(
        self,
        request: PredicateQueryRequest,
        subject_types: list[str] | None,
        return_fields: list[str] | None = None,
    ) -> Any: ...


class MongoFactRepository:
    """Reads DB-filtered materialized facts for indexed predicate retrieval."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def find_by_request(
        self,
        request: PredicateQueryRequest,
        subject_types: list[str] | None,
        return_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return matching facts using a MongoDB aggregation pipeline.

        Facts are stored one document per projected path, so the pipeline groups
        facts by logical DPP ID, applies every predicate to that grouped record,
        then unwinds only the matching groups. This keeps normal indexed
        predicate filtering inside MongoDB instead of fetching the whole index
        into Python and filtering there.
        """
        pipeline = _indexed_predicate_pipeline(request, subject_types, return_fields)
        return await self._db[FACT_COLLECTION].aggregate(pipeline).to_list(None)


class IndexedQueryMatcher:
    """Evaluate predicate retrieval from materialized attribute facts.

    Facts are the local indexed representation of the derived query view for
    current revisions. Indexing changes execution cost, not query semantics.
    """

    def __init__(self, repository: FactRepository) -> None:
        self._repository = repository

    async def matching_fact_groups(
        self,
        request: PredicateQueryRequest,
        subject_types: list[str] | None,
        return_fields: list[str] | None = None,
    ) -> list[dict[str, dict[str, Any]]]:
        """Return current local fact groups that satisfy every predicate."""
        facts = self._repository.find_by_request(request, subject_types, return_fields)
        if inspect.isawaitable(facts):
            facts = await facts
        grouped: OrderedDict[str, dict[str, dict[str, Any]]] = OrderedDict()
        for fact in facts:
            grouped.setdefault(fact["logical_dpp_id"], OrderedDict())[fact["path"]] = fact
        return list(grouped.values())

    async def select(self, request: PredicateQueryRequest, subject_types: list[str] | None) -> list[dict[str, Any]]:
        """Project requested attribute facts from each matching local group."""
        groups = await self.matching_fact_groups(request, subject_types, request.return_fields)
        return [_select_indexed_fields(group, request.return_fields) for group in groups]

    async def count(self, request: PredicateQueryRequest, subject_types: list[str] | None) -> int:
        """Count local fact groups that satisfy every predicate."""
        return len(await self.matching_fact_groups(request, subject_types))

    async def sum(self, request: PredicateQueryRequest, subject_types: list[str] | None) -> float:
        """Sum the requested numeric attribute fact over matching local groups."""
        total = 0.0
        for group in await self.matching_fact_groups(request, subject_types):
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
    requested_subject_types = await _resolve_requested_subject_types(db, request)

    if requested_subject_types == []:
        return empty_response(request, platform_id)

    if request.execution_mode is QueryExecutionMode.INDEXED:
        matcher: IndexedQueryMatcher | OnDemandQueryMatcher = IndexedQueryMatcher(MongoFactRepository(db))
    else:
        matcher = OnDemandQueryMatcher(await _current_payloads_for_subject_types(db, requested_subject_types))

    if request.result_mode is QueryResultMode.SELECT:
        return PredicateQueryResponse(
            result_mode=request.result_mode,
            execution_mode=request.execution_mode,
            platform_id=platform_id,
            matches=await matcher.select(request, requested_subject_types) if isinstance(matcher, IndexedQueryMatcher) else matcher.select(request),
        )
    if request.result_mode is QueryResultMode.COUNT:
        return PredicateQueryResponse(
            result_mode=request.result_mode,
            execution_mode=request.execution_mode,
            platform_id=platform_id,
            count=await matcher.count(request, requested_subject_types) if isinstance(matcher, IndexedQueryMatcher) else matcher.count(request),
        )
    return PredicateQueryResponse(
        result_mode=request.result_mode,
        execution_mode=request.execution_mode,
        platform_id=platform_id,
        aggregate=await matcher.sum(request, requested_subject_types) if isinstance(matcher, IndexedQueryMatcher) else matcher.sum(request),
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
    if request.subject_types is not None:
        for index, subject_type in enumerate(request.subject_types):
            if not subject_type or not subject_type.strip():
                raise ValueError(f"subject_types[{index}] must not be blank")
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


async def _resolve_requested_subject_types(
    db: AsyncIOMotorDatabase,
    request: PredicateQueryRequest,
) -> list[str] | None:
    """Return canonical restricted subject types, or ``None`` for all types."""
    if not request.subject_types:
        return None

    requested = {subject_type.lower(): subject_type for subject_type in request.subject_types}
    actual: list[str] = []
    async for subject_type in db.subject_types.find({}, {"_id": 0, "name": 1}):
        name = subject_type.get("name")
        if isinstance(name, str) and name.lower() in requested:
            actual.append(name)
    return actual


async def _current_payloads_for_subject_types(
    db: AsyncIOMotorDatabase,
    subject_types: list[str] | None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    query = {} if subject_types is None else {"subject_type": {"$in": subject_types}}
    async for logical_dpp in db.logical_dpps.find(query, {"_id": 0}):
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
        for document in await _current_payloads_for_subject_types(db, [source_scope.subject_type]):
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


def _indexed_predicate_pipeline(
    request: PredicateQueryRequest,
    subject_types: list[str] | None,
    return_fields: list[str] | None,
) -> list[dict[str, Any]]:
    """Build the one-fact-per-path MongoDB pipeline for indexed predicates."""
    pipeline: list[dict[str, Any]] = []
    if subject_types:
        pipeline.append({"$match": {"subject_type": {"$in": subject_types}}})

    pipeline.append(
        {
            "$group": {
                "_id": "$logical_dpp_id",
                "facts": {"$push": "$$ROOT"},
            }
        }
    )

    predicate_matches = [_predicate_group_match(filter_) for filter_ in request.filters]
    if predicate_matches:
        pipeline.append({"$match": {"$and": predicate_matches}})

    pipeline.extend(
        [
            {"$unwind": "$facts"},
            {"$replaceRoot": {"newRoot": "$facts"}},
        ]
    )
    if return_fields:
        pipeline.append({"$match": {"path": {"$in": return_fields}}})
    pipeline.extend(
        [
            {"$project": {"_id": 0}},
            {"$sort": {"logical_dpp_id": 1, "path": 1}},
        ]
    )
    return pipeline


def _predicate_group_match(filter_: PredicateFilter) -> dict[str, Any]:
    """Translate one predicate to a grouped-facts Mongo query fragment."""
    operator = filter_.operator
    if operator is PredicateOperator.NOT_EXISTS:
        return {
            "facts": {
                "$not": {
                    "$elemMatch": {
                        "path": filter_.path,
                        "$or": _fact_exists_conditions(),
                    }
                }
            }
        }

    elem_match: dict[str, Any] = {"path": filter_.path}
    if operator is PredicateOperator.EXISTS:
        elem_match["$or"] = _fact_exists_conditions()
    elif operator is PredicateOperator.EQ:
        elem_match.update(_or_conditions(_value_equal_conditions(filter_.value)))
    elif operator is PredicateOperator.NEQ:
        elem_match["$or"] = _fact_exists_conditions()
        equal_conditions = _value_equal_conditions(filter_.value)
        if equal_conditions:
            elem_match["$nor"] = equal_conditions
    elif operator is PredicateOperator.IN:
        values = filter_.value if isinstance(filter_.value, (list, tuple, set)) else []
        elem_match.update(_or_conditions(_value_equal_conditions_for_values(values)))
    elif operator in {PredicateOperator.GT, PredicateOperator.GTE, PredicateOperator.LT, PredicateOperator.LTE}:
        elem_match.update(_or_conditions(_ordered_value_conditions(operator, filter_.value)))
    else:
        raise ValueError(f"Unsupported predicate operator: {operator}")
    return {"facts": {"$elemMatch": elem_match}}


def _or_conditions(conditions: list[dict[str, Any]]) -> dict[str, Any]:
    if conditions:
        return {"$or": conditions}
    return {"__never_matches__": True}


def _fact_exists_conditions() -> list[dict[str, Any]]:
    return [
        {"value_text": {"$exists": True, "$ne": None}},
        {"value_number": {"$exists": True, "$ne": None}},
        {"value_boolean": {"$exists": True, "$ne": None}},
    ]


def _value_equal_conditions_for_values(values: Any) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for value in values:
        conditions.extend(_value_equal_conditions(value))
    return conditions


def _value_equal_conditions(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, bool):
        return [{"value_boolean": value}]
    if is_numeric(value):
        return [{"value_number": float(value)}]

    text = str(value)
    conditions: list[dict[str, Any]] = [{"value_text": text}]
    parsed_bool = _parse_bool_string(text)
    if parsed_bool is not None:
        conditions.append({"value_boolean": parsed_bool})
    parsed_number = _parse_number(text)
    if parsed_number is not None:
        conditions.append({"value_number": parsed_number})
    return conditions


def _ordered_value_conditions(operator: PredicateOperator, value: Any) -> list[dict[str, Any]]:
    mongo_operator = {
        PredicateOperator.GT: "$gt",
        PredicateOperator.GTE: "$gte",
        PredicateOperator.LT: "$lt",
        PredicateOperator.LTE: "$lte",
    }[operator]
    conditions: list[dict[str, Any]] = []
    parsed_number = _parse_number(value)
    if parsed_number is not None:
        conditions.append({"value_number": {mongo_operator: parsed_number}})
    elif value is not None:
        # ISO date and date-time facts are stored as strings; lexical ordering
        # matches chronological ordering for the normalized representations used
        # by the workload and query examples.
        conditions.append({"value_text": {mongo_operator: str(value)}})
    return conditions


def _parse_bool_string(value: str) -> bool | None:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return None


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if is_numeric(value):
        return float(value)
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


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
