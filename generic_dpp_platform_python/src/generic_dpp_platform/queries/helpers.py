"""Pure predicate and payload-projection helpers shared by both matchers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from numbers import Number
from typing import Any

from .models import PredicateFilter, PredicateOperator


def resolve_path(document: dict[str, Any] | None, path: str | None) -> Any | None:
    """Resolve a dot-separated path, returning ``None`` for a missing path.

    The Java helper deliberately uses ``null`` for both an absent path and a
    stored null.  Retaining that convention is important for NEQ, EXISTS, and
    NOT_EXISTS behaviour.
    """
    if document is None or path is None or not path.strip():
        return None

    current: Any = document
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def select_fields(document: dict[str, Any], return_fields: list[str] | None) -> dict[str, Any]:
    """Return the whole document or Java-style dotted-field projection."""
    if not return_fields:
        return document

    result: dict[str, Any] = {}
    for field in return_fields:
        value = resolve_path(document, field)
        if value is not None:
            result[field] = value
    return result


def matches_filter(document: dict[str, Any], filter_: PredicateFilter) -> bool:
    return matches_value(resolve_path(document, filter_.path), filter_)


def matches_value(document_value: Any | None, filter_: PredicateFilter) -> bool:
    """Evaluate one value using the Java ``PredicateFilterDTO`` semantics."""
    operator = filter_.operator
    predicate_value = filter_.value

    if operator is PredicateOperator.EQ:
        return _values_equal(document_value, predicate_value)
    if operator is PredicateOperator.NEQ:
        # Deliberately do not let NEQ turn a missing path into a match.
        return document_value is not None and not _values_equal(document_value, predicate_value)
    if operator is PredicateOperator.IN:
        if not isinstance(predicate_value, (list, tuple, set)):
            return False
        return any(_values_equal(document_value, value) for value in predicate_value)
    if operator is PredicateOperator.GT:
        return _compare(document_value, predicate_value) > 0
    if operator is PredicateOperator.GTE:
        return _compare(document_value, predicate_value) >= 0
    if operator is PredicateOperator.LT:
        return _compare(document_value, predicate_value) < 0
    if operator is PredicateOperator.LTE:
        return _compare(document_value, predicate_value) <= 0
    if operator is PredicateOperator.EXISTS:
        return document_value is not None
    if operator is PredicateOperator.NOT_EXISTS:
        return document_value is None
    raise ValueError(f"Unsupported predicate operator: {operator}")


def is_numeric(value: Any) -> bool:
    """Match Java's Number check (where Boolean is not a Number)."""
    return isinstance(value, Number) and not isinstance(value, bool)


def _values_equal(document_value: Any | None, predicate_value: Any | None) -> bool:
    if is_numeric(document_value) and predicate_value is not None:
        try:
            return Decimal(str(document_value)) == Decimal(str(predicate_value))
        except (InvalidOperation, ValueError):
            return False
    if isinstance(document_value, bool) and isinstance(predicate_value, str):
        return (document_value and predicate_value.lower() == "true") or (
            not document_value and predicate_value.lower() == "false"
        )
    return document_value == predicate_value


def _compare(document_value: Any | None, predicate_value: Any | None) -> int:
    if is_numeric(document_value) and predicate_value is not None:
        try:
            left = Decimal(str(document_value))
            right = Decimal(str(predicate_value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Value type mismatch: {document_value} vs {predicate_value}") from exc
        return (left > right) - (left < right)

    if document_value is None:
        raise ValueError("Value is not comparable: None")
    try:
        return (document_value > predicate_value) - (document_value < predicate_value)
    except TypeError as exc:
        raise ValueError(f"Value type mismatch: {document_value} vs {predicate_value}") from exc

