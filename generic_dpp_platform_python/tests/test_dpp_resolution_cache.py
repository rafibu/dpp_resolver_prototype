from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD
from generic_dpp_platform.dpps.exceptions import DppReferenceResolutionException
from generic_dpp_platform.dpps.models import DppRevisionResponseDTO, DppRevisionSchemaDTO
from generic_dpp_platform.dpps.utils import hash_document, hash_to_hex

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}
_SCHEMA_DTO = DppRevisionSchemaDTO(subject_type="pv_module", major_version=1, minor_version=0)


def _make_response(dpp_id: str, version: int, payload: dict) -> DppRevisionResponseDTO:
    return DppRevisionResponseDTO(
        dpp_id=dpp_id,
        version=version,
        schema_version=_SCHEMA_DTO,
        dpp_payload=payload,
        payload_hash=hash_to_hex(hash_document(payload)),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_failed_resolution_returns_424(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup, httpx_mock
):
    payload_with_ref = {
        **VALID_PV_PAYLOAD,
        "battery": {"$ref": "pv_module/issuerB-unreachable", "version": 1},
    }

    httpx_mock.add_response(
        url="http://resolver:8080/pv_module/issuerB-unreachable/1",
        status_code=404
    )

    response = await http_client.post(
        "/dpps/issue",
        json={
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_with_ref,
        },
    )

    assert response.status_code == 424
    assert response.json()["error"] == "Reference Resolution Failed"


@pytest.mark.asyncio
async def test_cache_hit_avoids_resolver_call(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup, httpx_mock
):
    external_payload = {**VALID_PV_PAYLOAD, "serial_number": "SN-ext-001"}

    # Pre-populate cache with a valid (correct hash) entry
    await test_db.referenced_dpp_revisions.insert_one(
        {
            "dpp_id": "issuerB-cached",
            "dpp_version": 1,
            "subject_type": "pv_module",
            "schema_subject_type": "pv_module",
            "schema_major_version": 1,
            "schema_minor_version": 0,
            "dpp_document": external_payload,
            "hashed_document": hash_to_hex(hash_document(external_payload)),
            "created_at": datetime.now(UTC),
            "fetched_at": datetime.now(UTC),
        }
    )

    payload_with_cached_ref = {
        **VALID_PV_PAYLOAD,
        "battery": {"$ref": "pv_module/issuerB-cached", "version": 1},
    }

    response = await http_client.post(
        "/dpps/issue",
        json={
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_with_cached_ref,
        },
    )

    assert response.status_code == 201

    # Verify no outgoing requests were made (because of cache hit)
    assert len(httpx_mock.get_requests()) == 0
