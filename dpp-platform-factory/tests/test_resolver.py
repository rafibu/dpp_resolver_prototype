"""
Unit tests use a mocked DockerClient.
Integration tests (marked integration) require a running Docker daemon
and the dpp-resolver:latest and postgres:16 images to be available.
"""
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from dpp_platform_factory.utils.config import ResolverConfig
from dpp_platform_factory.infrastructure.resolver import (
    RESOLVER_DB_NAME,
    RESOLVER_NAME,
    start_resolver,
    stop_resolver,
)
from dpp_platform_factory.core.state import PlatformStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_container(name: str, cid: str) -> MagicMock:
    c = MagicMock()
    c.name = name
    c.id = cid
    c.short_id = cid[:12]
    c.exec_run.return_value = (0, b"")
    return c


def _mock_docker_client(db_container=None, resolver_container=None) -> MagicMock:
    client = MagicMock()
    db = db_container or _mock_container(RESOLVER_DB_NAME, "db-cid-001")
    res = resolver_container or _mock_container(RESOLVER_NAME, "res-cid-001")
    client.run_container.side_effect = [db, res]
    client.wait_healthy.return_value = None
    return client, db, res


# ---------------------------------------------------------------------------
# start_resolver — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_resolver_spawns_db_first():
    client, db, _ = _mock_docker_client()
    config = ResolverConfig(port=8080)

    with patch("dpp_platform_factory.infrastructure.resolver._wait_postgres_ready", new_callable=AsyncMock):
        record = await start_resolver(client, "dpp-net", config)

    first_call = client.run_container.call_args_list[0]
    assert first_call[1]["name"] == RESOLVER_DB_NAME
    assert "postgres" in first_call[1]["image"]


@pytest.mark.asyncio
async def test_start_resolver_spawns_resolver_second():
    client, db, _ = _mock_docker_client()
    config = ResolverConfig(port=8080)

    with patch("dpp_platform_factory.infrastructure.resolver._wait_postgres_ready", new_callable=AsyncMock):
        record = await start_resolver(client, "dpp-net", config)

    second_call = client.run_container.call_args_list[1]
    assert second_call[1]["name"] == RESOLVER_NAME


@pytest.mark.asyncio
async def test_start_resolver_maps_host_port():
    client, _, _ = _mock_docker_client()
    config = ResolverConfig(port=9090)

    with patch("dpp_platform_factory.infrastructure.resolver._wait_postgres_ready", new_callable=AsyncMock):
        await start_resolver(client, "dpp-net", config)

    resolver_call = client.run_container.call_args_list[1]
    ports = resolver_call[1]["ports"]
    assert any(v == 9090 for v in ports.values())


@pytest.mark.asyncio
async def test_start_resolver_returns_record_with_correct_urls():
    client, db, res = _mock_docker_client()
    config = ResolverConfig(port=8080)

    with patch("dpp_platform_factory.infrastructure.resolver._wait_postgres_ready", new_callable=AsyncMock):
        record = await start_resolver(client, "dpp-net", config)

    assert record.external_url == "http://localhost:8080"
    assert "dpp-resolver" in record.internal_url
    assert record.status == PlatformStatus.RUNNING


@pytest.mark.asyncio
async def test_start_resolver_calls_wait_healthy():
    client, _, _ = _mock_docker_client()
    config = ResolverConfig(port=8080)

    with patch("dpp_platform_factory.infrastructure.resolver._wait_postgres_ready", new_callable=AsyncMock):
        await start_resolver(client, "dpp-net", config)

    client.wait_healthy.assert_called_once()
    args = client.wait_healthy.call_args
    assert "/health" in args[0][1]


@pytest.mark.asyncio
async def test_start_resolver_labels_both_containers():
    client, _, _ = _mock_docker_client()
    config = ResolverConfig(port=8080)

    with patch("dpp_platform_factory.infrastructure.resolver._wait_postgres_ready", new_callable=AsyncMock):
        await start_resolver(client, "dpp-net", config)

    for c in client.run_container.call_args_list:
        labels = c[1]["labels"]
        assert labels.get("managed-by") == "dpp-factory"


@pytest.mark.asyncio
async def test_start_resolver_db_env_has_credentials():
    client, _, _ = _mock_docker_client()
    config = ResolverConfig(port=8080)

    with patch("dpp_platform_factory.infrastructure.resolver._wait_postgres_ready", new_callable=AsyncMock):
        await start_resolver(client, "dpp-net", config)

    db_env = client.run_container.call_args_list[0][1]["env"]
    assert "POSTGRES_DB" in db_env
    assert "POSTGRES_USER" in db_env
    assert "POSTGRES_PASSWORD" in db_env


# ---------------------------------------------------------------------------
# stop_resolver — unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_resolver_stops_both_containers():
    from dpp_platform_factory.core.state import ResolverRecord
    from datetime import UTC, datetime

    client = MagicMock()
    mock_container = MagicMock()
    client._client.containers.get.return_value = mock_container

    record = ResolverRecord(
        container_id="res-cid",
        db_container_id="db-cid",
        external_url="http://localhost:8080",
        internal_url="http://dpp-resolver:8080",
        status=PlatformStatus.RUNNING,
        started_at=datetime.now(UTC),
    )

    await stop_resolver(client, record)

    assert client.stop_container.call_count == 2
    assert client.remove_container.call_count == 2


@pytest.mark.asyncio
async def test_stop_resolver_tolerates_missing_container():
    from dpp_platform_factory.core.state import ResolverRecord
    from datetime import UTC, datetime
    import docker.errors

    client = MagicMock()
    client._client.containers.get.side_effect = docker.errors.NotFound("gone")

    record = ResolverRecord(
        container_id="res-cid",
        db_container_id="db-cid",
        external_url="http://localhost:8080",
        internal_url="http://dpp-resolver:8080",
        status=PlatformStatus.RUNNING,
        started_at=datetime.now(UTC),
    )

    await stop_resolver(client, record)  # must not raise


# ---------------------------------------------------------------------------
# Integration test stubs (require Docker daemon + images)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skip(reason="Requires Docker daemon and dpp-resolver:latest image")
@pytest.mark.asyncio
async def test_integration_start_and_stop_resolver():
    """Bring up real Resolver + Postgres, verify health, tear down."""
    from dpp_platform_factory.infrastructure.docker_client import DockerClient as RealDockerClient
    client = RealDockerClient()
    network = client.ensure_network("dpp-net-test")
    config = ResolverConfig(port=18080)
    record = await start_resolver(client, network.name, config)
    assert record.status == PlatformStatus.RUNNING
    await stop_resolver(client, record)
