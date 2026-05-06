import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}
_DPP_ID = "issuerA-cur-rev-test"


@pytest.mark.asyncio
async def test_current_revision_returns_highest_version(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    base = {
        "dpp_id": _DPP_ID,
        "schema_version": _SCHEMA_VERSION,
        "dpp_payload": VALID_PV_PAYLOAD,
    }

    r1 = await http_client.post("/dpps", json=base)
    assert r1.status_code == 201

    r2 = await http_client.post(f"/dpps/{_DPP_ID}", json=base)
    assert r2.status_code == 201

    r3 = await http_client.post(f"/dpps/{_DPP_ID}", json=base)
    assert r3.status_code == 201

    current = await http_client.get(f"/dpps/{_DPP_ID}")
    assert current.status_code == 200
    assert current.json()["version"] == 3

    r4 = await http_client.post(f"/dpps/{_DPP_ID}", json=base)
    assert r4.status_code == 201

    current_after = await http_client.get(f"/dpps/{_DPP_ID}")
    assert current_after.json()["version"] == 4

    v2 = await http_client.get(f"/dpps/{_DPP_ID}/2")
    assert v2.status_code == 200
    assert v2.json()["version"] == 2


@pytest.mark.asyncio
async def test_get_nonexistent_dpp_returns_404(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.get("/dpps/issuerA-does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"] == "Not Found"
