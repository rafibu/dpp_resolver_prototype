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
async def test_direct_cycle_not_rejected_at_instance_level(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup, httpx_mock
):
    """Instance-level cycle detection is intentionally not enforced.

    Schema-level cycle prevention is the primary mechanism (Invariant I6, enforced by the
    resolver). At the instance level, issuerA-001 hard-refs issuerB-001/1 whose payload
    back-refs issuerA-001, but the issue operation succeeds because detect_cycles is not
    called from the normal issue path.
    """
    payload_with_cycle = {
        **VALID_PV_PAYLOAD,
        "battery": {"$ref": "pv_module/issuerB-001", "version": 1},
    }
    external_payload_back_ref = {
        **VALID_PV_PAYLOAD,
        "pv": {"$ref": "pv_module/issuerA-001", "version": 1},
    }

    httpx_mock.add_response(
        url="http://resolver:8080/pv_module/issuerB-001/1",
        json=_make_response("issuerB-001", 1, external_payload_back_ref).model_dump(mode="json"),
    )

    response = await http_client.post(
        "/dpps/issue",
        json={
            "dpp_id": "issuerA-001",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_with_cycle,
        },
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_transitive_cycle_not_rejected_at_instance_level(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup, httpx_mock
):
    """A -> B -> C -> A (3-hop): issue succeeds because instance-level cycle detection is not enforced.

    Only the direct hard references of A are resolved (B is fetched). The transitive
    dependency chain is not traversed during issue, so C is never fetched.
    """
    payload_a = {**VALID_PV_PAYLOAD, "b": {"$ref": "pv_module/issuerB-002", "version": 1}}
    payload_b = {**VALID_PV_PAYLOAD, "c": {"$ref": "pv_module/issuerC-001", "version": 1}}

    httpx_mock.add_response(
        url="http://resolver:8080/pv_module/issuerB-002/1",
        json=_make_response("issuerB-002", 1, payload_b).model_dump(mode="json"),
    )

    response = await http_client.post(
        "/dpps/issue",
        json={
            "dpp_id": "issuerA-trans",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_a,
        },
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_soft_references_do_not_trigger_cycle(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    """Soft references are not resolved during issue, so no external call is made."""
    payload_a_soft = {
        **VALID_PV_PAYLOAD,
        "battery": {"$ref": "pv_module/issuerB-soft"},  # soft - no version
    }

    response = await http_client.post(
        "/dpps/issue",
        json={
            "dpp_id": "issuerA-soft",
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload_a_soft,
        },
    )
    assert response.status_code == 201
