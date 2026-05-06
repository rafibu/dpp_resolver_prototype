import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}


@pytest.mark.asyncio
async def test_create_dpp_with_explicit_id_success(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.post(
        "/dpps",
        json={
            "dpp_id": "issuerA-123",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": VALID_PV_PAYLOAD,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["dpp_id"] == "issuerA-123"
    assert body["version"] == 1


@pytest.mark.asyncio
async def test_create_dpp_with_duplicate_explicit_id_conflict(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    payload = {
        "dpp_id": "issuerA-dup",
        "schema_version": _SCHEMA_VERSION,
        "dpp_payload": VALID_PV_PAYLOAD,
    }
    first = await http_client.post("/dpps", json=payload)
    assert first.status_code == 201

    second = await http_client.post("/dpps", json=payload)
    assert second.status_code == 409
    assert second.json()["error"] == "DPP Already Exists"


@pytest.mark.asyncio
async def test_create_dpp_with_invalid_issuer_prefix_bad_request(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.post(
        "/dpps",
        json={
            "dpp_id": "wrongIssuer-999",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": VALID_PV_PAYLOAD,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_dpp_without_explicit_id_generates_id(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.post(
        "/dpps",
        json={
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": VALID_PV_PAYLOAD,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["dpp_id"].startswith("issuerA")
    assert body["version"] == 1
