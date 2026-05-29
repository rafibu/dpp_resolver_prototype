from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from dpp_platform_factory.core.platform import PlatformRecord
from dpp_platform_factory.core.state import PlatformStatus
from dpp_platform_factory.infrastructure.resolver import ResolverRecord
from dpp_platform_factory.utils.bootstrap import bootstrap
from dpp_platform_factory.utils.config import FederationConfig, ResolverConfig, PlatformConfig


@pytest.mark.asyncio
async def test_bootstrap_success(mocker):
    # Mock DockerClient
    mock_client = MagicMock()
    mock_network = MagicMock()
    mock_network.name = "dpp-net"
    mock_client.ensure_network.return_value = mock_network

    # Mock config
    config = FederationConfig(
        resolver=ResolverConfig(port=8080),
        platforms=[
            PlatformConfig(
                platform_id="platform-a",
                stack="spring-postgres",
                issuer_id="issuer-a",
                subject_types=["type-a"],
                port=8081
            )
        ]
    )

    # Mock start_resolver
    mock_resolver_record = ResolverRecord(
        container_id="res-1",
        db_container_id="res-db-1",
        external_url="http://localhost:8080",
        internal_url="http://dpp-resolver:8080",
        status="RUNNING",
        started_at=datetime.now(UTC)
    )
    mocker.patch("dpp_platform_factory.utils.bootstrap.start_resolver", return_value=mock_resolver_record)

    # Mock spawn_platform
    mock_platform_record = PlatformRecord(
        platform_id="platform-a",
        stack="spring-postgres",
        issuer_id="issuer-a",
        subject_types=["type-a"],
        container_id="plat-1",
        db_container_id="plat-db-1",
        external_url="http://localhost:8081",
        internal_url="http://dpp-platform-a:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(UTC)
    )
    mocker.patch("dpp_platform_factory.utils.bootstrap.spawn_platform", return_value=mock_platform_record)

    # Mock ResolverClient
    mock_resolver_client = MagicMock()
    mock_resolver_client.ensure_subject_type = AsyncMock()
    mock_resolver_client.register_platform = AsyncMock()
    mocker.patch("dpp_platform_factory.utils.bootstrap.ResolverClient", return_value=mock_resolver_client)

    mocker.patch("dpp_platform_factory.utils.bootstrap.handle_orphans", new_callable=AsyncMock)

    state = await bootstrap(mock_client, config)

    assert state.resolver == mock_resolver_record
    assert "platform-a" in state.platforms
    assert state.platforms["platform-a"] == mock_platform_record
    mock_resolver_client.register_platform.assert_called_once_with(mock_platform_record)

@pytest.mark.asyncio
async def test_bootstrap_platform_failure_continues(mocker):
    # Mock DockerClient
    mock_client = MagicMock()
    mock_network = MagicMock()
    mock_network.name = "dpp-net"
    mock_client.ensure_network.return_value = mock_network

    # Mock config with two platforms
    config = FederationConfig(
        resolver=ResolverConfig(port=8080),
        platforms=[
            PlatformConfig(
                platform_id="platform-a",
                stack="spring-postgres",
                issuer_id="issuer-a",
                subject_types=["type-a"],
                port=8081
            ),
            PlatformConfig(
                platform_id="platform-b",
                stack="fastapi-mongo",
                issuer_id="issuer-b",
                subject_types=["type-b"],
                port=8082
            )
        ]
    )

    # Mock start_resolver
    mock_resolver_record = ResolverRecord(
        container_id="res-1",
        db_container_id="res-db-1",
        external_url="http://localhost:8080",
        internal_url="http://dpp-resolver:8080",
        status="RUNNING",
        started_at=datetime.now(UTC)
    )
    mocker.patch("dpp_platform_factory.utils.bootstrap.start_resolver", return_value=mock_resolver_record)

    # Mock spawn_platform: first fails, second succeeds
    mock_platform_record_b = PlatformRecord(
        platform_id="platform-b",
        stack="fastapi-mongo",
        issuer_id="issuer-b",
        subject_types=["type-b"],
        container_id="plat-b",
        db_container_id="plat-db-b",
        external_url="http://localhost:8082",
        internal_url="http://dpp-platform-b:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(UTC)
    )
    
    mock_spawn = AsyncMock()
    mock_spawn.side_effect = [Exception("Spawn failed"), mock_platform_record_b]
    mocker.patch("dpp_platform_factory.utils.bootstrap.spawn_platform", mock_spawn)

    # Mock ResolverClient
    mock_resolver_client = MagicMock()
    mock_resolver_client.ensure_subject_type = AsyncMock()
    mock_resolver_client.register_platform = AsyncMock()
    mocker.patch("dpp_platform_factory.utils.bootstrap.ResolverClient", return_value=mock_resolver_client)

    mocker.patch("dpp_platform_factory.utils.bootstrap.handle_orphans", new_callable=AsyncMock)

    state = await bootstrap(mock_client, config)

    assert state.resolver == mock_resolver_record
    assert state.platforms["platform-a"].status == PlatformStatus.ERROR
    assert state.platforms["platform-b"] == mock_platform_record_b
    mock_resolver_client.register_platform.assert_called_once_with(mock_platform_record_b)
