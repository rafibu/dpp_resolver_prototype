import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}


@pytest.mark.asyncio
async def test_schema_validation_failure_returns_structured_error(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.post(
        "/dpps/issue",
        json={
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": {"recycled_content": 10},  # missing required serial_number
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Schema Validation Failed"
    assert any("serial_number" in d for d in body["details"])
    assert "timestamp" in body
    assert "path" in body


@pytest.mark.asyncio
async def test_invalid_schema_version_returns_structured_error(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.post(
        "/dpps/issue",
        json={
            "schema_version": {"subject_type": "pv_module", "major_version": 99, "minor_version": 0},
            "dpp_payload": VALID_PV_PAYLOAD,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Invalid Argument"
    assert "Schema version not found" in body["message"]


@pytest.mark.asyncio
async def test_nonexistent_dpp_returns_structured_error(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.get("/dpps/issuerA-ghost-dpp")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "Not Found"
    assert "timestamp" in body
    assert "path" in body


@pytest.mark.asyncio
async def test_duplicate_dpp_id_returns_structured_error(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    payload = {
        "dpp_id": "issuerA-err-dup",
        "schema_version": _SCHEMA_VERSION,
        "dpp_payload": VALID_PV_PAYLOAD,
    }
    first = await http_client.post("/dpps/issue", json=payload)
    assert first.status_code == 201

    second = await http_client.post("/dpps/issue", json=payload)
    assert second.status_code == 409
    assert second.json()["error"] == "DPP Already Exists"
