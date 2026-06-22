"""GET /query/predicate, compatible with the Java QueryController."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError
from typing import Any

from .models import PredicateQueryRequest, PredicateQueryResponse
from .service import query_predicate
from ..database import get_database

router = APIRouter()
_FILTER_PARAM = re.compile(r"^filters\[(\d+)]\.(path|operator|value)$")


@router.get("/predicate", response_model=PredicateQueryResponse)
async def query_predicate_endpoint(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PredicateQueryResponse:
    """Evaluate a predicate query using Java-style query parameter binding."""
    return await query_predicate(db, _parse_request(request))


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
