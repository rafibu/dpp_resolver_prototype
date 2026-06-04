import asyncio
import pymongo
import pytest
import pytest_asyncio
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

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


class ReplicaSetMongoDbContainer(DockerContainer):
    """MongoDB container configured as a single-node replica set.

    The standard MongoDbContainer runs as a standalone server, which rejects multi-document
    transactions. This subclass passes --replSet to the MongoDB command and initiates the
    replica set after the server is ready, enabling the transactions used by the DPP service.
    """

    _PORT = 27017

    def __init__(self, image: str = "mongo:8") -> None:
        super().__init__(image)
        self.with_command("--replSet rs0 --bind_ip_all")
        self.with_exposed_ports(self._PORT)

    def get_connection_url(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self._PORT)
        return f"mongodb://{host}:{port}/?directConnection=true"

    def start(self) -> "ReplicaSetMongoDbContainer":
        super().start()
        wait_for_logs(self, "Waiting for connections")
        self._initiate_replica_set()
        return self

    def _initiate_replica_set(self) -> None:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(self._PORT)
        client = pymongo.MongoClient(f"mongodb://{host}:{port}/?directConnection=true")
        try:
            client.admin.command(
                "replSetInitiate",
                {"_id": "rs0", "members": [{"_id": 0, "host": "localhost:27017"}]},
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    status = client.admin.command("replSetGetStatus")
                    if any(m.get("stateStr") == "PRIMARY" for m in status.get("members", [])):
                        return
                except Exception:
                    pass
                time.sleep(0.5)
            raise TimeoutError("Timed out waiting for replica set primary election")
        finally:
            client.close()


@pytest.fixture(scope="session")
def mongodb_container():
    with ReplicaSetMongoDbContainer("mongo:8") as container:
        yield container


@pytest_asyncio.fixture
async def test_db(mongodb_container: ReplicaSetMongoDbContainer) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    client: AsyncIOMotorClient = AsyncIOMotorClient(mongodb_container.get_connection_url())
    await _wait_for_writable_primary(client)

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


async def _wait_for_writable_primary(client: AsyncIOMotorClient, timeout_seconds: float = 30.0) -> None:
    """Wait until the async Mongo client sees the single-node replica set as writable."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            hello = await client.admin.command("hello")
            if hello.get("isWritablePrimary") or hello.get("ismaster"):
                return
        except Exception as exc:
            last_error = exc

        await asyncio.sleep(0.2)

    raise TimeoutError("Timed out waiting for MongoDB writable primary") from last_error


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
