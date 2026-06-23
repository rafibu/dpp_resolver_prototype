from __future__ import annotations

import pytest
from generic_dpp_platform.queries.index import (
    replace_materialized_facts,
    replace_materialized_references,
)


async def _insert_current_source(
    db,
    *,
    dpp_id: str,
    payload: dict,
) -> None:
    await db.logical_dpps.insert_one(
        {"dpp_id": dpp_id, "subject_type": "pv_module", "current_version": 1}
    )
    await db.dpp_revisions.insert_one(
        {"dpp_id": dpp_id, "dpp_version": 1, "dpp_document": payload}
    )
    await replace_materialized_facts(db, dpp_id, "pv_module", payload)
    await replace_materialized_references(db, dpp_id, "pv_module", payload)


@pytest.mark.asyncio
async def test_traverse_endpoint_uses_current_reference_index_and_on_demand_payloads(
    test_db, http_client
) -> None:
    await test_db.subject_types.insert_one({"name": "pv_module"})
    matching_payload = {
        "name": "Module A",
        "workload_s4": {"source_dpp_id": "issuer-module-a"},
        "components": {"primary": {"$ref": "component/issuer-component-1/3"}},
    }
    non_matching_payload = {
        "name": "Module B",
        "workload_s4": {"source_dpp_id": "issuer-module-b"},
        "components": {"primary": {"$ref": "component/issuer-component-1/2"}},
    }
    await _insert_current_source(test_db, dpp_id="issuer-module-a", payload=matching_payload)
    await _insert_current_source(test_db, dpp_id="issuer-module-b", payload=non_matching_payload)

    params = [
        ("subjectType", "component"),
        ("dppId", "issuer-component-1"),
        ("revisionNumber", "3"),
        ("sources[0].subjectType", "pv_module"),
        ("sources[0].referencePaths[0]", "components.primary"),
    ]
    indexed = await http_client.get("/query/traverse", params=[("executionMode", "INDEXED"), *params])
    on_demand = await http_client.get("/query/traverse", params=[("executionMode", "ON_DEMAND"), *params])

    assert indexed.status_code == 200
    assert on_demand.status_code == 200
    assert indexed.json()["platform_id"] == "issuerA"
    assert indexed.json()["subject_type"] == "component"
    assert indexed.json()["dpp_id"] == "issuer-component-1"
    assert len(indexed.json()["matches"]) == 1
    # Java's indexed matcher is flattened while on-demand returns the original
    # source payload; both identify the same current source DPP.
    assert indexed.json()["matches"][0]["workload_s4.source_dpp_id"] == "issuer-module-a"
    assert on_demand.json()["matches"] == [matching_payload]


@pytest.mark.asyncio
async def test_replacing_current_reference_materialization_removes_stale_target(test_db) -> None:
    first = {"component": {"$ref": "component/issuer-component-old/1"}}
    revised = {"component": {"$ref": "component/issuer-component-new/2"}}

    await replace_materialized_references(test_db, "issuer-module-a", "pv_module", first)
    await replace_materialized_references(test_db, "issuer-module-a", "pv_module", revised)

    assert await test_db.dpp_reference.count_documents(
        {"source_logical_dpp_id": "issuer-module-a"}
    ) == 1
    current = await test_db.dpp_reference.find_one({"source_logical_dpp_id": "issuer-module-a"})
    assert current["target_dpp_id"] == "issuer-component-new"
    assert current["target_revision_number"] == 2
