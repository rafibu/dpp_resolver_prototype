"""HTTP boundary for platform-local predicate retrieval and reverse traversal."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError
from typing import Any

from .models import (
    PredicateQueryRequest,
    PredicateQueryResponse,
    TraverseQueryRequest,
    TraverseQueryResponse,
)
from .service import query_predicate, query_traverse
from ..database import get_database

router = APIRouter()
_FILTER_PARAM = re.compile(r"^filters\[(\d+)]\.(path|operator|value)$")
_TRAVERSE_SOURCE_PARAM = re.compile(r"^sources\[(\d+)]\.(subjectType|subject_type)$")
_TRAVERSE_REFERENCE_PATH_PARAM = re.compile(
    r"^sources\[(\d+)]\.(referencePaths|reference_paths)(?:\[(\d+)])?$"
)


@router.get("/predicate", response_model=PredicateQueryResponse)
async def query_predicate_endpoint(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PredicateQueryResponse:
    """Evaluate predicate retrieval over this platform's current revisions.

    Federation-wide routing and result merging remain outside this endpoint.
    """
    return await query_predicate(db, _parse_request(request))


@router.get("/traverse", response_model=TraverseQueryResponse)
async def query_traverse_endpoint(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TraverseQueryResponse:
    """Find local current source revisions that reference the requested target.

    The caller supplies schema-level source scopes; this endpoint does not
    perform resolver routing or federation-wide traversal.
    """
    return await query_traverse(db, _parse_traverse_request(request))


def _parse_request(request: Request) -> PredicateQueryRequest:
    params = request.query_params
    filters: dict[int, dict[str, Any]] = defaultdict(dict)
    filter_values: dict[tuple[int, str], list[str]] = defaultdict(list)

    for key, value in params.multi_items():
        match = _FILTER_PARAM.match(key)
        if match:
            filter_values[(int(match.group(1)), match.group(2))].append(value)

    for (index, field), values in filter_values.items():
        if field == "value":
            filters[index][field] = _coerce_filter_value(values)
        else:
            filters[index][field] = values[-1]

    data: dict[str, Any] = {
        "result_mode": _first(params, "resultMode", "result_mode"),
        "execution_mode": _first(params, "executionMode", "execution_mode") or "INDEXED",
        "subject_type": _first(params, "subjectType", "subject_type"),
        "filters": [filters[index] for index in sorted(filters)],
        "return_fields": _all(params, "returnFields", "return_fields") or None,
        "aggregate_path": _first(params, "aggregatePath", "aggregate_path"),
    }
    try:
        return PredicateQueryRequest.model_validate(data)
    except ValidationError as exc:
        # The Java controller responds with a 400 for invalid @ModelAttribute
        # binding; routing through the application's ValueError handler does
        # the same here.
        raise ValueError(str(exc)) from exc


def _parse_traverse_request(request: Request) -> TraverseQueryRequest:
    params = request.query_params
    sources: dict[int, dict[str, Any]] = defaultdict(dict)
    reference_paths: dict[int, list[str]] = defaultdict(list)

    for key, value in params.multi_items():
        source_match = _TRAVERSE_SOURCE_PARAM.match(key)
        if source_match:
            sources[int(source_match.group(1))]["subject_type"] = value
            continue
        path_match = _TRAVERSE_REFERENCE_PATH_PARAM.match(key)
        if path_match:
            reference_paths[int(path_match.group(1))].append(value)

    for index, paths in reference_paths.items():
        sources[index]["reference_paths"] = paths

    data: dict[str, Any] = {
        "execution_mode": _first(params, "executionMode", "execution_mode") or "INDEXED",
        "subject_type": _first(params, "subjectType", "subject_type"),
        "dpp_id": _first(params, "dppId", "dpp_id"),
        "revision_number": _first(params, "revisionNumber", "revision_number"),
        # Java's ``@NotNull`` accepts [] but rejects an omitted parameter.
        "sources": [sources[index] for index in sorted(sources)] if sources else None,
    }
    try:
        return TraverseQueryRequest.model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def _first(params: Any, *names: str) -> str | None:
    for name in names:
        value = params.get(name)
        if value is not None:
            return value
    return None


def _all(params: Any, *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        values.extend(params.getlist(name))
    return values


def _coerce_filter_value(values: list[str]) -> Any:
    if len(values) > 1:
        return values
    if not values:
        return None
    value = values[0]
    # Supporting JSON here is additive, while plain repeated query parameters
    # retain the Java controller's IN request shape.
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return value
