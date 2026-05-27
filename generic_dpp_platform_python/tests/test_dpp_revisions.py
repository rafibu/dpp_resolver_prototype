import asyncio

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}


def _base_request(dpp_id: str | None = None) -> dict:
    req = {"schema_version": _SCHEMA_VERSION, "dpp_payload": VALID_PV_PAYLOAD}
    if dpp_id:
        req["dpp_id"] = dpp_id
    return req


@pytest.mark.asyncio
async def test_revision_flow_success(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    dpp_id = "issuerA-rev-flow"

    # Create revision 1
    r1 = await http_client.post("/dpps/issue", json={**_base_request(dpp_id), "version": 1})
    assert r1.status_code == 201
    assert r1.json()["version"] == 1

    # Append revision 2 with explicit version
    r2 = await http_client.post(
        f"/dpps/{dpp_id}/revise",
        json={**_base_request(), "version": 2},
    )
    assert r2.status_code == 201
    assert r2.json()["version"] == 2

    # Verify revision 1 unchanged
    v1 = await http_client.get(f"/dpps/{dpp_id}/1")
    assert v1.status_code == 200
    assert v1.json()["version"] == 1

    # Append revision 3 without specifying version (auto-increment)
    r3 = await http_client.post(f"/dpps/{dpp_id}/revise", json=_base_request())
    assert r3.status_code == 201
    assert r3.json()["version"] == 3

    # Skipped version (5) returns 409
    r_skip = await http_client.post(
        f"/dpps/{dpp_id}/revise",
        json={**_base_request(), "version": 5},
    )
    assert r_skip.status_code == 409

    # Old version (2) also returns 409
    r_old = await http_client.post(
        f"/dpps/{dpp_id}/revise",
        json={**_base_request(), "version": 2},
    )
    assert r_old.status_code == 409


@pytest.mark.asyncio
async def test_concurrency_appends(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    dpp_id = "issuerA-concurrency"

    # Create initial revision
    r = await http_client.post("/dpps/issue", json=_base_request(dpp_id))
    assert r.status_code == 201

    # 5 concurrent appends without specifying version
    async def append():
        return await http_client.post(f"/dpps/{dpp_id}/revise", json=_base_request())

    results = await asyncio.gather(*[append() for _ in range(5)])

    statuses = [r.status_code for r in results]
    assert all(s == 201 for s in statuses), f"Not all succeeded: {statuses}"

    versions = {r.json()["version"] for r in results}
    assert versions == {2, 3, 4, 5, 6}
