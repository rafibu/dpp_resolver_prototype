from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD
from generic_dpp_platform.dpps.models import DppRevisionResponseDTO, DppRevisionSchemaDTO

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}

_SCHEMA_DTO = DppRevisionSchemaDTO(subject_type="pv_module", major_version=1, minor_version=0)


def _make_response(dpp_id: str, version: int, payload: dict) -> DppRevisionResponseDTO:
    from datetime import UTC, datetime
    return DppRevisionResponseDTO(
        dpp_id=dpp_id,
        version=version,
        schema_version=_SCHEMA_DTO,
        dpp_payload=payload,
        payload_hash="a" * 64,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_direct_cycle_is_rejected(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup, httpx_mock
):
    """issuerA-001 hard-refs issuerB-001/1; issuerB-001/1 hard-refs back issuerA-001 -> cycle."""
    payload_with_cycle = {
        **VALID_PV_PAYLOAD,
        "battery": {"$ref": "pv_module/issuerB-001", "version": 1},
    }
    external_payload_back_ref = {
        **VALID_PV_PAYLOAD,
        "pv": {"$ref": "pv_module/issuerA-001", "version": 1},
    }

    mock_response = _make_response("issuerB-001", 1, external_payload_back_ref)
    
    httpx_mock.add_response(
        url="http://resolver:8080/pv_module/issuerB-001/1",
        json=mock_response.model_dump(mode="json")
    )

    response = await http_client.post(
        "/dpps",
        json={
            "dpp_id": "issuerA-001",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_with_cycle,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "Cycle Detected"


@pytest.mark.asyncio
async def test_transitive_cycle_is_rejected(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup, httpx_mock
):
    """A -> B -> C -> A (3-hop cycle)."""
    payload_a = {**VALID_PV_PAYLOAD, "b": {"$ref": "pv_module/issuerB-002", "version": 1}}
    payload_b = {**VALID_PV_PAYLOAD, "c": {"$ref": "pv_module/issuerC-001", "version": 1}}
    payload_c = {**VALID_PV_PAYLOAD, "a": {"$ref": "pv_module/issuerA-trans", "version": 1}}

    httpx_mock.add_response(
        url="http://resolver:8080/pv_module/issuerB-002/1",
        json=_make_response("issuerB-002", 1, payload_b).model_dump(mode="json")
    )
    httpx_mock.add_response(
        url="http://resolver:8080/pv_module/issuerC-001/1",
        json=_make_response("issuerC-001", 1, payload_c).model_dump(mode="json")
    )

    response = await http_client.post(
        "/dpps",
        json={
            "dpp_id": "issuerA-trans",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_a,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "Cycle Detected"


@pytest.mark.asyncio
async def test_soft_references_do_not_trigger_cycle(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    """A -> B (soft), B -> A (hard): no cycle because soft refs are ignored in detection."""
    payload_a_soft = {
        **VALID_PV_PAYLOAD,
        "battery": {"$ref": "pv_module/issuerB-soft"},  # soft - no version
    }

    response = await http_client.post(
        "/dpps",
        json={
            "dpp_id": "issuerA-soft",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_a_soft,
        },
    )
    assert response.status_code == 201
