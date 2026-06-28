from __future__ import annotations

import json
import pytest
from datetime import UTC, datetime
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from typing import Any

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}
_DEFAULT_QUERY_SUBJECT_TYPES = ("pv_module",)


def _payload(
    name: str,
    serial_number: str,
    chemistry: str,
    *,
    weight_kg: int | None = None,
    recyclable: bool,
    country: str | None = None,
    capacity_kwh: int | str = 55,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "serial_number": serial_number,
        "manufacturer": "Acme",
        "chemistry": chemistry,
        "capacity_kwh": capacity_kwh,
        "recyclable": recyclable,
    }
    if weight_kg is not None:
        payload["weight_kg"] = weight_kg
    if country is not None:
        payload["manufacturer_details"] = {"country": country}
    return payload


async def _issue(http_client: AsyncClient, dpp_id: str, payload: dict[str, Any], subject_type: str = "pv_module") -> None:
    response = await http_client.post(
        "/dpps/issue",
        json={
            "dpp_id": dpp_id,
            "schema_version": {**_SCHEMA_VERSION, "subject_type": subject_type},
            "dpp_payload": payload,
        },
    )
    assert response.status_code == 201, response.text


async def _revise(http_client: AsyncClient, dpp_id: str, payload: dict[str, Any]) -> None:
    response = await http_client.post(
        f"/dpps/{dpp_id}/revise",
        json={"version": 2, "schema_version": _SCHEMA_VERSION, "dpp_payload": payload},
    )
    assert response.status_code == 201, response.text


async def _seed_current_batteries(http_client: AsyncClient) -> None:
    await _issue(
        http_client,
        "issuerA-battery-1",
        _payload("Battery A old", "A-OLD", "LFP", weight_kg=300, recyclable=True, country="DE", capacity_kwh=45),
    )
    await _revise(
        http_client,
        "issuerA-battery-1",
        _payload("Battery A", "A-001", "NMC", weight_kg=320, recyclable=True, country="CH"),
    )
    await _issue(
        http_client,
        "issuerA-battery-2",
        _payload("Battery B", "B-001", "LFP", weight_kg=410, recyclable=False, country="DE", capacity_kwh=75),
    )
    await _issue(
        http_client,
        "issuerA-battery-3",
        _payload("Battery C", "C-001", "NMC", weight_kg=500, recyclable=True, country="US", capacity_kwh=95),
    )
    await _issue(
        http_client,
        "issuerA-battery-4",
        _payload("Battery D", "D-001", "LTO", recyclable=True, capacity_kwh=30),
    )
    await _issue(
        http_client,
        "issuerA-battery-5",
        _payload("Battery E", "E-001", "NMC", weight_kg=350, recyclable=False, country="CH", capacity_kwh="not-a-number"),
    )


async def _query(
    http_client: AsyncClient,
    result_mode: str,
    execution_mode: str,
    *,
    subject_types: tuple[str, ...] | list[str] | None = _DEFAULT_QUERY_SUBJECT_TYPES,
    filters: list[dict[str, Any]] | None = None,
    return_fields: list[str] | None = None,
    aggregate_path: str | None = None,
) -> Any:
    params: list[tuple[str, str]] = [
        ("resultMode", result_mode),
        ("executionMode", execution_mode),
    ]
    for subject_type in subject_types or []:
        params.append(("subjectTypes", subject_type))
    for index, filter_ in enumerate(filters or []):
        params.extend(
            [
                (f"filters[{index}].path", filter_["path"]),
                (f"filters[{index}].operator", filter_["operator"]),
            ]
        )
        if "value" in filter_:
            values = filter_["value"] if isinstance(filter_["value"], list) else [filter_["value"]]
            params.extend((f"filters[{index}].value", str(value).lower() if isinstance(value, bool) else str(value)) for value in values)
    for field in return_fields or []:
        params.append(("returnFields", field))
    if aggregate_path is not None:
        params.append(("aggregatePath", aggregate_path))
    return await http_client.get("/query/predicate", params=params)


async def _register_schema(test_db: AsyncIOMotorDatabase, subject_type: str) -> None:
    await test_db.subject_types.insert_one({"name": subject_type, "description": None})
    await test_db.schemas.insert_one(
        {
            "subject_type": subject_type,
            "major_version": 1,
            "minor_version": 0,
            "schema_document": {"type": "object", "additionalProperties": True},
            "published_at": datetime.now(UTC),
        }
    )


@pytest.mark.asyncio
async def test_issue_and_revise_materialize_current_facts_and_create_required_indexes(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
    pv_setup,
) -> None:
    await _seed_current_batteries(http_client)

    current_serial_fact = await test_db.query_attribute_fact.find_one(
        {"logical_dpp_id": "issuerA-battery-1", "path": "serial_number"}
    )
    assert current_serial_fact is not None
    assert current_serial_fact["value_text"] == "A-001"
    assert await test_db.query_attribute_fact.count_documents(
        {"logical_dpp_id": "issuerA-battery-1", "path": "serial_number", "value_text": "A-OLD"}
    ) == 0

    facts = await test_db.query_attribute_fact.find({}).to_list(None)
    assert facts
    for fact in facts:
        assert sum(fact.get(field) is not None for field in ("value_text", "value_number", "value_boolean")) == 1

    indexes = {index["name"]: index for index in await test_db.query_attribute_fact.list_indexes().to_list(None)}
    assert {"uq_qaf_logical_dpp_path", "idx_qaf_subject_path", "idx_qaf_text_lookup", "idx_qaf_number_lookup", "idx_qaf_boolean_lookup"} <= set(indexes)
    assert indexes["uq_qaf_logical_dpp_path"]["unique"] is True

    duplicate = {key: value for key, value in current_serial_fact.items() if key != "_id"}
    with pytest.raises(DuplicateKeyError):
        await test_db.query_attribute_fact.insert_one(duplicate)


@pytest.mark.asyncio
async def test_indexed_and_on_demand_select_are_equivalent_and_match_java_http_contract(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
    pv_setup,
) -> None:
    await _seed_current_batteries(http_client)
    query_kwargs = {
        "filters": [{"path": "serial_number", "operator": "EQ", "value": "A-001"}],
        "return_fields": ["name", "capacity_kwh", "manufacturer_details.country"],
    }
    indexed = await _query(http_client, "SELECT", "INDEXED", **query_kwargs)
    on_demand = await _query(http_client, "SELECT", "ON_DEMAND", **query_kwargs)

    assert indexed.status_code == on_demand.status_code == 200
    expected_matches = [{"name": "Battery A", "capacity_kwh": 55, "manufacturer_details.country": "CH"}]
    assert indexed.json() == {
        "result_mode": "SELECT",
        "execution_mode": "INDEXED",
        "platform_id": "issuerA",
        "count": None,
        "aggregate": None,
        "matches": expected_matches,
    }
    assert on_demand.json() == {
        "result_mode": "SELECT",
        "execution_mode": "ON_DEMAND",
        "platform_id": "issuerA",
        "count": None,
        "aggregate": None,
        "matches": expected_matches,
    }
    # Compare logical results across modes; each response must still report the
    # execution mode it actually used.
    assert indexed.json()["execution_mode"] == "INDEXED"
    assert on_demand.json()["execution_mode"] == "ON_DEMAND"

    # The Java controller is GET /query/predicate.  No ObjectId/native Mongo
    # identifier is exposed by the Java-compatible API JSON.
    assert (await http_client.post("/query/predicate", json={})).status_code == 405
    assert '"_id"' not in json.dumps(indexed.json())
    assert await test_db.query_attribute_fact.count_documents({}) > 5


@pytest.mark.asyncio
async def test_on_demand_recomputes_from_stored_payload_while_indexed_uses_materialized_facts(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
    pv_setup,
) -> None:
    await _seed_current_batteries(http_client)
    await test_db.dpp_revisions.update_one(
        {"dpp_id": "issuerA-battery-1", "dpp_version": 2},
        {"$set": {"dpp_document.chemistry": "LFP"}},
    )

    filters = [{"path": "chemistry", "operator": "EQ", "value": "LFP"}]
    indexed = await _query(http_client, "COUNT", "INDEXED", filters=filters)
    on_demand = await _query(http_client, "COUNT", "ON_DEMAND", filters=filters)

    assert indexed.json()["count"] == 1
    assert on_demand.json()["count"] == 2


@pytest.mark.asyncio
async def test_predicate_operators_count_sum_and_filterless_current_dpps(
    http_client: AsyncClient,
    pv_setup,
) -> None:
    await _seed_current_batteries(http_client)

    async def count(filters: list[dict[str, Any]], mode: str = "INDEXED") -> int:
        response = await _query(http_client, "COUNT", mode, filters=filters)
        assert response.status_code == 200, response.text
        return response.json()["count"]

    assert await count([]) == 5  # current logical DPPs, never materialized fact rows
    assert await count([{"path": "chemistry", "operator": "EQ", "value": "NMC"}]) == 3
    assert await count([{"path": "chemistry", "operator": "NEQ", "value": "NMC"}]) == 2
    assert await count([{"path": "manufacturer_details.country", "operator": "EXISTS"}]) == 4
    assert await count([{"path": "manufacturer_details.country", "operator": "NOT_EXISTS"}]) == 1
    assert await count([{"path": "does.not.exist", "operator": "EQ", "value": "anything"}]) == 0
    assert await count([{"path": "does.not.exist", "operator": "NEQ", "value": "anything"}]) == 0
    assert await count([{"path": "does.not.exist", "operator": "NOT_EXISTS"}]) == 5
    assert await count(
        [
            {"path": "chemistry", "operator": "EQ", "value": "NMC"},
            {"path": "manufacturer_details.country", "operator": "EQ", "value": "CH"},
            {"path": "recyclable", "operator": "EQ", "value": True},
        ]
    ) == 1

    sum_all = await _query(http_client, "SUM", "INDEXED", aggregate_path="weight_kg")
    sum_filtered = await _query(
        http_client,
        "SUM",
        "ON_DEMAND",
        filters=[{"path": "recyclable", "operator": "EQ", "value": True}],
        aggregate_path="weight_kg",
    )
    assert sum_all.json()["aggregate"] == 1580.0
    assert sum_filtered.json()["aggregate"] == 820.0

    missing_sum = await _query(
        http_client,
        "SUM",
        "INDEXED",
        filters=[{"path": "serial_number", "operator": "EQ", "value": "D-001"}],
        aggregate_path="weight_kg",
    )
    assert missing_sum.json()["aggregate"] == 0.0

    non_numeric = await _query(
        http_client,
        "SUM",
        "ON_DEMAND",
        filters=[{"path": "serial_number", "operator": "EQ", "value": "E-001"}],
        aggregate_path="capacity_kwh",
    )
    assert non_numeric.status_code == 400


@pytest.mark.asyncio
async def test_subject_types_omitted_single_and_multiple_match_same_predicates(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
    pv_setup,
) -> None:
    await _seed_current_batteries(http_client)
    await _register_schema(test_db, "battery")
    await _issue(
        http_client,
        "issuerA-pack-1",
        _payload("Pack A", "PACK-001", "NMC", weight_kg=100, recyclable=True, country="CH"),
        subject_type="battery",
    )

    filters = [{"path": "chemistry", "operator": "EQ", "value": "NMC"}]
    omitted = await _query(http_client, "COUNT", "INDEXED", subject_types=None, filters=filters)
    empty = await _query(http_client, "COUNT", "ON_DEMAND", subject_types=[], filters=filters)
    pv_only = await _query(http_client, "COUNT", "INDEXED", subject_types=["pv_module"], filters=filters)
    both = await _query(http_client, "COUNT", "ON_DEMAND", subject_types=["pv_module", "battery"], filters=filters)

    assert omitted.json()["count"] == 4
    assert empty.json()["count"] == 4
    assert pv_only.json()["count"] == 3
    assert both.json()["count"] == 4


@pytest.mark.asyncio
async def test_cross_type_factory_date_query_is_equivalent_indexed_and_on_demand(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
    pv_setup,
) -> None:
    await _register_schema(test_db, "battery")
    await _issue(
        http_client,
        "issuerA-pv-factory-a",
        {
            "serial_number": "PV-A",
            "manufacturer": "Acme",
            "manufacturing": {"facilityId": "factory-a", "date": "2024-06-01"},
        },
    )
    await _issue(
        http_client,
        "issuerA-pack-factory-a",
        {
            "serial_number": "BAT-A",
            "manufacturer": "Acme",
            "manufacturing": {"facilityId": "factory-a", "date": "2024-07-15"},
        },
        subject_type="battery",
    )
    await _issue(
        http_client,
        "issuerA-pv-factory-b",
        {
            "serial_number": "PV-B",
            "manufacturer": "Acme",
            "manufacturing": {"facilityId": "factory-b", "date": "2024-07-01"},
        },
    )

    query_kwargs = {
        "subject_types": None,
        "filters": [
            {"path": "manufacturing.facilityId", "operator": "EQ", "value": "factory-a"},
            {"path": "manufacturing.date", "operator": "GTE", "value": "2024-01-01"},
            {"path": "manufacturing.date", "operator": "LTE", "value": "2024-12-31"},
        ],
        "return_fields": ["serial_number", "manufacturing.facilityId", "manufacturing.date"],
    }
    indexed = await _query(http_client, "SELECT", "INDEXED", **query_kwargs)
    on_demand = await _query(http_client, "SELECT", "ON_DEMAND", **query_kwargs)

    assert indexed.status_code == on_demand.status_code == 200
    assert sorted(match["serial_number"] for match in indexed.json()["matches"]) == ["BAT-A", "PV-A"]
    assert sorted(match["serial_number"] for match in on_demand.json()["matches"]) == ["BAT-A", "PV-A"]


@pytest.mark.asyncio
async def test_sum_requires_aggregate_path_and_unknown_subject_type_has_empty_java_shape(
    http_client: AsyncClient,
    pv_setup,
) -> None:
    missing_aggregate = await http_client.get(
        "/query/predicate",
        params={"resultMode": "SUM", "executionMode": "INDEXED", "subjectType": "pv_module"},
    )
    assert missing_aggregate.status_code == 400

    unknown = await http_client.get(
        "/query/predicate",
        params={"resultMode": "COUNT", "executionMode": "ON_DEMAND", "subjectTypes": "unknown"},
    )
    assert unknown.status_code == 200
    assert unknown.json() == {
        "result_mode": "COUNT",
        "execution_mode": "ON_DEMAND",
        "platform_id": "issuerA",
        "count": 0,
        "aggregate": None,
        "matches": None,
    }
