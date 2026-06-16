import pytest
from datetime import UTC, datetime
from generic_dpp_platform.dpps.utils import hash_document, hash_to_hex
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}


@pytest.mark.asyncio
async def test_import_revisions_stores_revision_readable_through_dpp_endpoint(
    http_client: AsyncClient,
    pv_setup,
) -> None:
    dpp_id = "issuerB-import-001"
    response = await http_client.post(
        "/admin/import-revisions",
        json=[_revision(dpp_id, VALID_PV_PAYLOAD, _hash(VALID_PV_PAYLOAD))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["dpp_id"] == dpp_id
    assert body[0]["version"] == 1

    stored = await http_client.get(f"/dpps/{dpp_id}/1")
    assert stored.status_code == 200
    stored_body = stored.json()
    assert stored_body["dpp_payload"] == VALID_PV_PAYLOAD
    assert stored_body["payload_hash"] == _hash(VALID_PV_PAYLOAD)


@pytest.mark.asyncio
async def test_import_revisions_retry_is_idempotent(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
    pv_setup,
) -> None:
    dpp_id = "issuerB-import-retry"
    payload = _revision(dpp_id, VALID_PV_PAYLOAD, _hash(VALID_PV_PAYLOAD))

    first = await http_client.post("/admin/import-revisions", json=[payload])
    second = await http_client.post("/admin/import-revisions", json=[payload])

    assert first.status_code == 200
    assert second.status_code == 200
    assert await test_db.dpp_revisions.count_documents({"dpp_id": dpp_id}) == 1


@pytest.mark.asyncio
async def test_import_revisions_rejects_payload_hash_mismatch(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
    pv_setup,
) -> None:
    dpp_id = "issuerB-import-bad-hash"
    response = await http_client.post(
        "/admin/import-revisions",
        json=[_revision(dpp_id, VALID_PV_PAYLOAD, "00")],
    )

    assert response.status_code == 400
    assert "payload hash mismatch" in response.json()["message"]
    assert await test_db.logical_dpps.count_documents({"dpp_id": dpp_id}) == 0
    assert await test_db.dpp_revisions.count_documents({"dpp_id": dpp_id}) == 0


@pytest.mark.asyncio
async def test_import_revisions_requires_cached_schema(
    http_client: AsyncClient,
    test_db: AsyncIOMotorDatabase,
) -> None:
    await test_db.subject_types.insert_one({"name": "pv_module", "description": None})
    response = await http_client.post(
        "/admin/import-revisions",
        json=[_revision("issuerB-import-missing-schema", VALID_PV_PAYLOAD, _hash(VALID_PV_PAYLOAD))],
    )

    assert response.status_code == 400
    assert "Schema not cached" in response.json()["message"]


def _revision(dpp_id: str, payload: dict, payload_hash: str) -> dict:
    return {
        "dpp_id": dpp_id,
        "version": 1,
        "schema_version": _SCHEMA_VERSION,
        "dpp_payload": payload,
        "payload_hash": payload_hash,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    }


def _hash(payload: dict) -> str:
    return hash_to_hex(hash_document(payload))
