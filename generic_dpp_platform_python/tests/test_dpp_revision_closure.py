import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from conftest import VALID_PV_PAYLOAD

_SCHEMA_VERSION = {"subject_type": "pv_module", "major_version": 1, "minor_version": 0}
_SUBJECT_TYPE = "pv_module"


def _payload(serial_number: str, **extra: object) -> dict:
    return {**VALID_PV_PAYLOAD, "serial_number": serial_number, **extra}


def _hard_ref(dpp_id: str) -> dict:
    return {"$ref": f"{_SUBJECT_TYPE}/{dpp_id}", "version": 1}


async def _issue(http_client: AsyncClient, dpp_id: str, payload: dict) -> dict:
    response = await http_client.post(
        "/dpps/issue",
        json={
            "dpp_id": dpp_id,
            "version": 1,
            "schema_version": _SCHEMA_VERSION,
            "dpp_payload": payload,
        },
    )
    assert response.status_code == 201
    return response.json()


async def _create_chain(http_client: AsyncClient) -> tuple[str, str, str]:
    root = "issuerA-closure-a"
    middle = "issuerA-closure-b"
    leaf = "issuerA-closure-c"

    await _issue(http_client, leaf, _payload("SN-closure-c"))
    await _issue(http_client, middle, _payload("SN-closure-b", dependency=_hard_ref(leaf)))
    await _issue(http_client, root, _payload("SN-closure-a", dependency=_hard_ref(middle)))

    return root, middle, leaf


def _resolved_ids(body: dict) -> list[str]:
    return [revision["dpp_id"] for revision in body["resolved_revisions"]]


@pytest.mark.asyncio
async def test_closure_max_depth_one_resolves_only_direct_hard_references(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    root, middle, _ = await _create_chain(http_client)

    response = await http_client.get(f"/dpps/{root}/1/closure?max_depth=1")

    assert response.status_code == 200
    body = response.json()
    assert body["root_revision"]["dpp_id"] == root
    assert _resolved_ids(body) == [middle]


@pytest.mark.asyncio
async def test_closure_max_depth_two_resolves_transitive_hard_references(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    root, middle, leaf = await _create_chain(http_client)

    response = await http_client.get(f"/dpps/{root}/1/closure?max_depth=2")

    assert response.status_code == 200
    body = response.json()
    assert body["root_revision"]["dpp_id"] == root
    assert _resolved_ids(body) == [middle, leaf]


@pytest.mark.asyncio
async def test_closure_skips_duplicate_hard_references(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    root = "issuerA-closure-duplicate-root"
    dependency = "issuerA-closure-duplicate-dependency"

    await _issue(http_client, dependency, _payload("SN-duplicate-dependency"))
    await _issue(
        http_client,
        root,
        _payload(
            "SN-duplicate-root",
            dependencies=[_hard_ref(dependency), _hard_ref(dependency)],
        ),
    )

    response = await http_client.get(f"/dpps/{root}/1/closure?max_depth=1")

    assert response.status_code == 200
    assert _resolved_ids(response.json()) == [dependency]


@pytest.mark.asyncio
async def test_closure_rejects_invalid_max_depth(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    response = await http_client.get("/dpps/issuerA-missing/1/closure?max_depth=0")

    assert response.status_code == 422
    assert any("max_depth" in str(detail["loc"]) for detail in response.json()["detail"])


@pytest.mark.asyncio
async def test_direct_revision_endpoint_behavior_is_unchanged(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase, pv_setup
):
    root, _, _ = await _create_chain(http_client)

    response = await http_client.get(f"/dpps/{root}/1")

    assert response.status_code == 200
    body = response.json()
    assert body["dpp_id"] == root
    assert body["version"] == 1
    assert "root_revision" not in body
    assert "resolved_revisions" not in body
