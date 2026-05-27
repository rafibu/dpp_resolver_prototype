from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

PV_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://schemas.dpp.eu/pv_module/1.0",
    "type": "object",
    "properties": {
        "recycled_content": {"type": "number"},
        "manufacturer": {"type": "string"},
    },
    "required": ["recycled_content", "manufacturer"],
}


async def _seed_subject_type(db: AsyncIOMotorDatabase, name: str) -> None:
    await db.subject_types.insert_one({"name": name, "description": None})


async def _seed_schema(
    db: AsyncIOMotorDatabase,
    subject_type: str,
    major: int,
    minor: int,
) -> None:
    await db.schemas.insert_one(
        {
            "subject_type": subject_type,
            "major_version": major,
            "minor_version": minor,
            "schema_document": PV_SCHEMA_DOC,
            "published_at": datetime.now(UTC),
        }
    )


@pytest.mark.asyncio
async def test_get_current_schema_returns_newest(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase
) -> None:
    await _seed_subject_type(test_db, "pv_module")
    await _seed_schema(test_db, "pv_module", 1, 0)
    await _seed_schema(test_db, "pv_module", 1, 1)
    await _seed_schema(test_db, "pv_module", 2, 0)

    response = await http_client.get("/schemas/pv_module")
    assert response.status_code == 200
    body = response.json()
    assert body["major_version"] == 2
    assert body["minor_version"] == 0
    assert body["subject_type"] == "pv_module"


@pytest.mark.asyncio
async def test_get_current_schema_unknown_subject_type_returns_404(
    http_client: AsyncClient,
) -> None:
    response = await http_client.get("/schemas/unknown_type")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_current_schema_no_schema_yet_returns_404(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase
) -> None:
    await _seed_subject_type(test_db, "inverter")
    response = await http_client.get("/schemas/inverter")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_exact_schema_happy_path(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase
) -> None:
    await _seed_subject_type(test_db, "battery")
    await _seed_schema(test_db, "battery", 1, 0)
    await _seed_schema(test_db, "battery", 1, 1)

    response = await http_client.get("/schemas/battery/1/0")
    assert response.status_code == 200
    body = response.json()
    assert body["major_version"] == 1
    assert body["minor_version"] == 0


@pytest.mark.asyncio
async def test_get_exact_schema_unknown_version_returns_404(
    http_client: AsyncClient, test_db: AsyncIOMotorDatabase
) -> None:
    await _seed_subject_type(test_db, "inverter2")
    await _seed_schema(test_db, "inverter2", 1, 0)

    response = await http_client.get("/schemas/inverter2/9/9")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_exact_schema_unknown_subject_type_returns_404(
    http_client: AsyncClient,
) -> None:
    response = await http_client.get("/schemas/no_such_type/1/0")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cache_schema_unknown_subject_type_returns_400(
    http_client: AsyncClient,
) -> None:
    response = await http_client.post("/schemas/no_such_type/cacheSchema")
    assert response.status_code == 400
