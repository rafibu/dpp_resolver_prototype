from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from testcontainers.mongodb import MongoDbContainer

PV_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://schemas.dpp.eu/pv_module/1.0",
    "type": "object",
    "properties": {
        "serial_number": {"type": "string"},
        "recycled_content": {"type": "number", "minimum": 0, "maximum": 100},
        "manufacturer": {"type": "string"},
        "components": {
            "type": "object",
            "properties": {
                "battery": {"type": "object"},
                "inverter": {"type": "object"},
            },
        },
    },
    "required": ["serial_number", "manufacturer"],
    "additionalProperties": True,
}

VALID_PV_PAYLOAD = {
    "serial_number": "SN-001",
    "manufacturer": "SolarCo",
    "recycled_content": 35.0,
}


@pytest.fixture(scope="session")
def mongodb_container():
    with MongoDbContainer("mongo:8") as container:
        yield container


@pytest_asyncio.fixture
async def test_db(mongodb_container: MongoDbContainer) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    client: AsyncIOMotorClient = AsyncIOMotorClient(mongodb_container.get_connection_url())
    db: AsyncIOMotorDatabase = client["test_dpp_platform"]

    await db.subject_types.create_index("name", unique=True)
    await db.schemas.create_index(
        [("subject_type", 1), ("major_version", 1), ("minor_version", 1)],
        unique=True,
    )
    await db.logical_dpps.create_index("dpp_id", unique=True)
    await db.dpp_revisions.create_index(
        [("dpp_id", 1), ("dpp_version", 1)], unique=True
    )
    await db.dpp_revisions.create_index([("dpp_id", 1), ("dpp_version", -1)])
    await db.referenced_dpp_revisions.create_index(
        [("dpp_id", 1), ("dpp_version", 1)], unique=True
    )

    await db.platform_config.insert_one(
        {
            "platform_name": "Test Platform",
            "base_url": "http://localhost:8082",
            "issuer_id": "issuerA",
            "resolver_base_url": "http://resolver:8080",
        }
    )

    yield db

    await client.drop_database("test_dpp_platform")
    client.close()


@pytest_asyncio.fixture
async def http_client(test_db: AsyncIOMotorDatabase) -> AsyncGenerator[AsyncClient, None]:
    from generic_dpp_platform.database import get_database
    from generic_dpp_platform.main import app

    async def override_db() -> AsyncIOMotorDatabase:
        return test_db

    app.dependency_overrides[get_database] = override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def pv_setup(test_db: AsyncIOMotorDatabase) -> None:
    """Seed a pv_module subject type and schema 1.0 for DPP tests."""
    await test_db.subject_types.insert_one({"name": "pv_module", "description": None})
    await test_db.schemas.insert_one(
        {
            "subject_type": "pv_module",
            "major_version": 1,
            "minor_version": 0,
            "schema_document": PV_SCHEMA_DOC,
            "published_at": datetime.now(UTC),
        }
    )
