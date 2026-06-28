"""Semantic validation that pydantic field typing alone cannot express.

These checks enforce result-mode-specific fields and operator-specific value
rules. The query client validates request *shape*; it never interprets missing
values or evaluates predicates - that remains the platform's responsibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import (
    FederatedPredicateQueryRequest,
    PredicateFilter,
    PredicateOperator,
    QueryResultMode,
)


class QueryValidationError(ValueError):
    """Raised when a federated query request is semantically invalid."""


_SCALAR_REQUIRED = {PredicateOperator.EQ, PredicateOperator.NEQ}
_NUMERIC_REQUIRED = {
    PredicateOperator.GT,
    PredicateOperator.GTE,
    PredicateOperator.LT,
    PredicateOperator.LTE,
}
_NO_VALUE = {PredicateOperator.EXISTS, PredicateOperator.NOT_EXISTS}


def validate_request(request: FederatedPredicateQueryRequest) -> None:
    """Validate the semantics of a federated predicate query request.

    Raises :class:`QueryValidationError` on the first violation found.
    """
    for index, subject_type in enumerate(request.subject_types or []):
        if not subject_type or not subject_type.strip():
            raise QueryValidationError(f"subject_types[{index}] must not be blank")
    _validate_result_mode_fields(request)
    for index, filter_ in enumerate(request.filters):
        _validate_filter(filter_, index)


def _validate_result_mode_fields(request: FederatedPredicateQueryRequest) -> None:
    mode = request.result_mode

    # return_fields is only valid for SELECT.
    if request.return_fields is not None and mode is not QueryResultMode.SELECT:
        raise QueryValidationError(
            "return_fields is only valid for result_mode SELECT"
        )

    # aggregate_path is required for SUM and forbidden otherwise.
    if mode is QueryResultMode.SUM:
        if not request.aggregate_path:
            raise QueryValidationError("aggregate_path is required for result_mode SUM")
    elif request.aggregate_path is not None:
        raise QueryValidationError(
            "aggregate_path must not be provided for result_mode SELECT or COUNT"
        )


def _validate_filter(filter_: PredicateFilter, index: int) -> None:
    where = f"filters[{index}] ({filter_.operator.value})"

    # path and operator are guaranteed present by pydantic typing; guard empties.
    if not filter_.path:
        raise QueryValidationError(f"{where}: path must not be empty")

    operator = filter_.operator
    value = filter_.value

    if operator in _NO_VALUE:
        if value is not None:
            raise QueryValidationError(
                f"{where}: {operator.value} must not be given a value"
            )
        return

    if operator in _SCALAR_REQUIRED:
        _require_scalar(value, where)
        return

    if operator in _NUMERIC_REQUIRED:
        _require_ordered_scalar(value, where)
        return

    if operator is PredicateOperator.IN:
        _require_non_empty_array(value, where)
        return


def _require_scalar(value: Any, where: str) -> None:
    if value is None:
        raise QueryValidationError(f"{where}: a scalar value is required")
    if isinstance(value, (list, tuple, dict)):
        raise QueryValidationError(f"{where}: value must be a single scalar")


def _require_ordered_scalar(value: Any, where: str) -> None:
    if value is None:
        raise QueryValidationError(f"{where}: a numeric or ISO date value is required")
    if isinstance(value, bool) or isinstance(value, (list, tuple, dict)):
        raise QueryValidationError(f"{where}: value must be a single numeric or ISO date scalar")
    if isinstance(value, (int, float)):
        return
    if isinstance(value, str):
        if _is_numeric_string(value) or _is_iso_date(value):
            return
    raise QueryValidationError(f"{where}: value must be numeric or an ISO date/date-time")


def _require_non_empty_array(value: Any, where: str) -> None:
    if not isinstance(value, (list, tuple)):
        raise QueryValidationError(f"{where}: IN requires an array value")
    if len(value) == 0:
        raise QueryValidationError(f"{where}: IN requires a non-empty array value")


def _is_numeric_string(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _is_iso_date(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    try:
        if "T" not in text:
            datetime.strptime(text, "%Y-%m-%d")
            return True
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False
