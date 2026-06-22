"""Materialize current DPP payloads as MongoDB query-attribute facts."""

from __future__ import annotations

import re
from decimal import Decimal
from motor.motor_asyncio import AsyncIOMotorDatabase
from numbers import Number
from typing import Any

FACT_COLLECTION = "query_attribute_fact"
_VALUE_FIELDS = ("value_text", "value_number", "value_boolean")


def project_payload_to_facts(
    payload: dict[str, Any],
    logical_dpp_id: str,
    subject_type: str,
) -> list[dict[str, Any]]:
    """Project a payload using the Java materialized-index path rules.

    There is at most one fact for a logical DPP/path.  This mirrors the Java
    table primary key and means repeated projected list paths retain the last
    projected value.
    """
    facts: dict[str, dict[str, Any]] = {}
    _flatten_mapping(payload, "", logical_dpp_id, subject_type, facts)
    return list(facts.values())


def validate_fact_document(fact: dict[str, Any]) -> None:
    """Ensure a materialized fact satisfies Java's one-value-column invariant."""
    if not fact.get("logical_dpp_id") or not fact.get("path"):
        raise ValueError("A query attribute fact requires logical_dpp_id and path")
    populated = [field for field in _VALUE_FIELDS if fact.get(field) is not None]
    if len(populated) != 1:
        raise ValueError("A query attribute fact must contain exactly one populated value field")


async def replace_materialized_facts(
    db: AsyncIOMotorDatabase,
    logical_dpp_id: str,
    subject_type: str,
    payload: dict[str, Any],
    *,
    session: Any | None = None,
) -> None:
    """Replace the current fact set for one logical DPP.

    Callers performing issue/revise pass their MongoDB transaction session, so
    the current revision and its materialization become visible together.
    """
    facts = project_payload_to_facts(payload, logical_dpp_id, subject_type)
    for fact in facts:
        validate_fact_document(fact)

    collection = db[FACT_COLLECTION]
    await collection.delete_many({"logical_dpp_id": logical_dpp_id}, session=session)
    if facts:
        await collection.insert_many(facts, ordered=True, session=session)


def _flatten_mapping(
    document: dict[str, Any],
    prefix: str,
    logical_dpp_id: str,
    subject_type: str,
    facts: dict[str, dict[str, Any]],
) -> None:
    for key, value in document.items():
        path = key if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            _flatten_mapping(value, path, logical_dpp_id, subject_type, facts)
        elif isinstance(value, list):
            _project_list(value, path, logical_dpp_id, subject_type, facts)
        else:
            _add_fact(path, value, logical_dpp_id, subject_type, facts)


def _project_list(
    values: list[Any],
    path: str,
    logical_dpp_id: str,
    subject_type: str,
    facts: dict[str, dict[str, Any]],
) -> None:
    for value in values:
        if isinstance(value, dict):
            _project_object_item(value, path, logical_dpp_id, subject_type, facts)
        else:
            _add_fact(
                f"{path}.contains_{_normalize_path_segment(_java_string(value))}",
                True,
                logical_dpp_id,
                subject_type,
                facts,
            )


def _project_object_item(
    item: dict[str, Any],
    path: str,
    logical_dpp_id: str,
    subject_type: str,
    facts: dict[str, dict[str, Any]],
) -> None:
    text_values: list[str] = []
    scalar_values: dict[str, Any] = {}

    for field_name, value in item.items():
        if isinstance(value, str) and value.strip():
            text_values.append(_normalize_path_segment(value))
        elif isinstance(value, bool) or _is_number(value):
            scalar_values[_normalize_path_segment(field_name)] = value
        elif isinstance(value, dict):
            _flatten_mapping(value, f"{path}.{_normalize_path_segment(field_name)}", logical_dpp_id, subject_type, facts)
        elif isinstance(value, list):
            _project_list(value, f"{path}.{_normalize_path_segment(field_name)}", logical_dpp_id, subject_type, facts)

    for text_value in text_values:
        _add_fact(f"{path}.contains_{text_value}", True, logical_dpp_id, subject_type, facts)
        for scalar_name, scalar_value in scalar_values.items():
            _add_fact(
                f"{path}.{text_value}_{scalar_name}",
                scalar_value,
                logical_dpp_id,
                subject_type,
                facts,
            )


def _add_fact(
    path: str,
    value: Any,
    logical_dpp_id: str,
    subject_type: str,
    facts: dict[str, dict[str, Any]],
) -> None:
    fact = _create_fact(path, value, logical_dpp_id, subject_type)
    if fact is not None:
        facts[path] = fact


def _create_fact(
    path: str,
    value: Any,
    logical_dpp_id: str,
    subject_type: str,
) -> dict[str, Any] | None:
    if value is None or not path.strip():
        return None
    fact: dict[str, Any] = {
        "logical_dpp_id": logical_dpp_id,
        "subject_type": subject_type,
        "path": path,
    }
    if isinstance(value, bool):
        fact["value_boolean"] = value
    elif _is_number(value):
        # JSON payloads use int/float. Decimal is converted because PyMongo
        # requires Decimal128 explicitly, whereas Java's BigDecimal is native.
        fact["value_number"] = float(value) if isinstance(value, Decimal) else value
    elif isinstance(value, str):
        fact["value_text"] = value
    else:
        fact["value_text"] = _java_string(value)
    return fact


def _is_number(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _normalize_path_segment(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return normalized.strip("_")


def _java_string(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)
