"""Unit tests for platform lifecycle (mocked Docker)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dpp_platform_factory.core.platform import (
    PlatformSpec,
    _database_url,
    _db_env_and_mount,
    _platform_labels,
    spawn_platform,
    teardown_platform,
)
from dpp_platform_factory.core.state import PlatformStatus


def _mock_container(name: str, cid: str) -> MagicMock:
    c = MagicMock()
    c.name = name
    c.id = cid
    c.short_id = cid[:12]
    c.exec_run.return_value = (0, b"")
    return c


def _default_spec(stack: str = "spring-postgres", port: int = 8081) -> PlatformSpec:
    return PlatformSpec(
        platform_id="platform-a",
        stack=stack,
        issuer_id="issuerA",
        subject_types=["pv_module"],
        host_port=port,
    )


def _mock_client(db_cid="db-cid", plat_cid="plat-cid") -> MagicMock:
    client = MagicMock()
    db = _mock_container("dpp-platform-a-db", db_cid)
    plat = _mock_container("dpp-platform-a", plat_cid)
    client.run_container.side_effect = [db, plat]
    client.wait_healthy.return_value = None
    return client, db, plat


# ---------------------------------------------------------------------------
# spawn_platform — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_platform_returns_record():
    client, _, _ = _mock_client()
    spec = _default_spec()

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        record = await spawn_platform(client, "dpp-net", "http://resolver:8080", spec)

    assert record.platform_id == "platform-a"
    assert record.status == PlatformStatus.RUNNING


@pytest.mark.asyncio
async def test_spawn_platform_db_spawned_first():
    client, _, _ = _mock_client()

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        await spawn_platform(client, "dpp-net", "http://resolver:8080", _default_spec())

    first = client.run_container.call_args_list[0][1]
    assert "db" in first["name"]


@pytest.mark.asyncio
async def test_spawn_platform_platform_container_has_env_vars():
    client, _, _ = _mock_client()
    spec = _default_spec()

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        await spawn_platform(client, "dpp-net", "http://resolver:8080", spec)

    second = client.run_container.call_args_list[1][1]
    env = second["env"]
    assert env["PLATFORM_ID"] == "platform-a"
    assert env["ISSUER_ID"] == "issuerA"
    assert env["RESOLVER_URL"] == "http://resolver:8080"
    assert "pv_module" in env["SUBJECT_TYPES"]


@pytest.mark.asyncio
async def test_spawn_platform_subject_types_comma_separated():
    client = MagicMock()
    db = _mock_container("dpp-platform-a-db", "db")
    plat = _mock_container("dpp-platform-a", "plat")
    client.run_container.side_effect = [db, plat]

    spec = PlatformSpec(
        platform_id="platform-a",
        stack="spring-postgres",
        issuer_id="issuerA",
        subject_types=["pv_module", "junction_box"],
        host_port=8081,
    )
    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        await spawn_platform(client, "dpp-net", "http://resolver:8080", spec)

    env = client.run_container.call_args_list[1][1]["env"]
    assert env["SUBJECT_TYPES"] == "pv_module,junction_box"


@pytest.mark.asyncio
async def test_spawn_platform_external_url_uses_host_port():
    client, _, _ = _mock_client()

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        record = await spawn_platform(client, "dpp-net", "http://resolver:8080", _default_spec(port=8099))

    assert "8099" in record.external_url


@pytest.mark.asyncio
async def test_spawn_platform_internal_url_uses_container_name():
    client, _, _ = _mock_client()

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        record = await spawn_platform(client, "dpp-net", "http://resolver:8080", _default_spec())

    assert "dpp-platform-a" in record.internal_url


@pytest.mark.asyncio
async def test_spawn_platform_calls_wait_healthy():
    client, _, _ = _mock_client()

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        await spawn_platform(client, "dpp-net", "http://resolver:8080", _default_spec())

    client.wait_healthy.assert_called_once()
    assert "/health" in client.wait_healthy.call_args[0][1]


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_platform_labels_contain_managed_by():
    client, _, _ = _mock_client()

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        await spawn_platform(client, "dpp-net", "http://resolver:8080", _default_spec())

    for call in client.run_container.call_args_list:
        assert call[1]["labels"]["managed-by"] == "dpp-factory"


def test_platform_labels_contain_all_metadata():
    labels = _platform_labels("platform-a", "spring-postgres", "issuerA", ["pv_module"], 8081)
    assert labels["dpp-factory-platform-id"] == "platform-a"
    assert labels["dpp-factory-stack"] == "spring-postgres"
    assert labels["dpp-factory-issuer-id"] == "issuerA"
    assert "pv_module" in labels["dpp-factory-subject-types"]
    assert labels["dpp-factory-host-port"] == "8081"


# ---------------------------------------------------------------------------
# Cleanup on failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_platform_cleans_up_on_health_check_failure():
    client = MagicMock()
    db = _mock_container("dpp-platform-a-db", "db")
    plat = _mock_container("dpp-platform-a", "plat")
    client.run_container.side_effect = [db, plat]
    client.wait_healthy.side_effect = TimeoutError("health timeout")

    with patch("dpp_platform_factory.core.platform._wait_db_ready", new_callable=AsyncMock):
        with pytest.raises(TimeoutError):
            await spawn_platform(client, "dpp-net", "http://resolver:8080", _default_spec())

    client.stop_container.assert_called()
    client.remove_container.assert_called()


@pytest.mark.asyncio
async def test_spawn_platform_cleans_up_db_if_db_start_fails():
    client = MagicMock()
    db = _mock_container("dpp-platform-a-db", "db")
    client.run_container.return_value = db

    with patch(
        "dpp_platform_factory.core.platform._wait_db_ready",
        new_callable=AsyncMock,
        side_effect=TimeoutError("db timeout"),
    ):
        with pytest.raises(TimeoutError):
            await spawn_platform(client, "dpp-net", "http://resolver:8080", _default_spec())

    client.stop_container.assert_called()


# ---------------------------------------------------------------------------
# Database URL and image selection
# ---------------------------------------------------------------------------


def test_database_url_postgres():
    url = _database_url("spring-postgres", "dpp-platform-a-db")
    assert url.startswith("jdbc:postgresql://")
    assert "dpp-platform-a-db" in url


def test_database_url_mongo():
    url = _database_url("fastapi-mongo", "dpp-platform-a-db")
    assert url.startswith("mongodb://")


def test_db_env_and_mount_postgres():
    env, mount = _db_env_and_mount("spring-postgres")
    assert "POSTGRES_DB" in env
    assert "postgresql" in mount.lower() or "postgres" in mount.lower()


def test_db_env_and_mount_mongo():
    env, mount = _db_env_and_mount("fastapi-mongo")
    assert "/data/db" in mount


# ---------------------------------------------------------------------------
# teardown_platform
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_teardown_platform_stops_both_containers():
    from dpp_platform_factory.core.state import PlatformRecord
    from datetime import UTC, datetime

    client = MagicMock()
    client._client.containers.get.return_value = MagicMock()

    record = PlatformRecord(
        platform_id="platform-a",
        stack="spring-postgres",
        issuer_id="issuerA",
        subject_types=["pv_module"],
        container_id="plat-cid",
        db_container_id="db-cid",
        external_url="http://localhost:8081",
        internal_url="http://dpp-platform-a:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(UTC),
    )

    await teardown_platform(client, record)

    assert client.stop_and_remove_by_id.call_count == 2
