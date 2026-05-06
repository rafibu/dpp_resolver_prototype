import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD
from generic_dpp_platform.dpps.utils import hash_document, hash_to_hex, verify_hash_integrity


def test_hash_is_deterministic():
    h1 = hash_document(VALID_PV_PAYLOAD)
    h2 = hash_document(VALID_PV_PAYLOAD)
    assert h1 == h2


def test_hash_to_hex_is_64_chars():
    h = hash_to_hex(hash_document(VALID_PV_PAYLOAD))
    assert isinstance(h, str)
    assert len(h) == 64


def test_verify_hash_integrity_valid():
    doc = {"serial_number": "SN-001", "manufacturer": "SolarCo"}
    expected_hex = hash_to_hex(hash_document(doc))
    assert verify_hash_integrity(doc, expected_hex) is True


def test_verify_hash_integrity_tampered():
    doc = {"serial_number": "SN-001", "manufacturer": "SolarCo"}
    expected_hex = hash_to_hex(hash_document(doc))
    tampered_doc = {"serial_number": "SN-001", "manufacturer": "EvilCo"}
    assert verify_hash_integrity(tampered_doc, expected_hex) is False


@pytest.mark.asyncio
async def test_response_hash_is_hex_and_recomputable(
    http_client, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.post(
        "/dpps",
        json={
            "schema_version": {"subject_type": "pv_module", "major_version": 1, "minor_version": 0},
            "dpp_payload": VALID_PV_PAYLOAD,
        },
    )
    assert response.status_code == 201
    body = response.json()
    payload_hash = body["payload_hash"]
    assert isinstance(payload_hash, str)
    assert len(payload_hash) == 64

    recomputed = hash_to_hex(hash_document(body["dpp_payload"]))
    assert recomputed == payload_hash


@pytest.mark.asyncio
async def test_revision_endpoint_hash_consistency(
    http_client, test_db: AsyncIOMotorDatabase, pv_setup
):
    create_resp = await http_client.post(
        "/dpps",
        json={
            "dpp_id": "issuerA-hash-test",
            "schema_version": {"subject_type": "pv_module", "major_version": 1, "minor_version": 0},
            "dpp_payload": VALID_PV_PAYLOAD,
        },
    )
    assert create_resp.status_code == 201
    dpp_id = create_resp.json()["dpp_id"]
    original_hash = create_resp.json()["payload_hash"]

    current_resp = await http_client.get(f"/dpps/{dpp_id}")
    assert current_resp.json()["payload_hash"] == original_hash

    versioned_resp = await http_client.get(f"/dpps/{dpp_id}/1")
    assert versioned_resp.json()["payload_hash"] == original_hash
