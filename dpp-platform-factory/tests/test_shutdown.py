import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from dpp_platform_factory.utils.shutdown import shutdown
from dpp_platform_factory.core.state import FactoryState, ResolverRecord, PlatformRecord, PlatformStatus
from datetime import datetime, UTC

@pytest.mark.asyncio
async def test_shutdown_success(mocker):
    mock_client = MagicMock()
    # Mock container objects
    mock_plat_cont = MagicMock()
    mock_db_cont = MagicMock()
    mock_res_cont = MagicMock()
    mock_res_db_cont = MagicMock()
    
    mock_client._client.containers.get.side_effect = lambda cid: {
        "plat-1": mock_plat_cont,
        "db-1": mock_db_cont,
        "res-1": mock_res_cont,
        "res-db-1": mock_res_db_cont
    }[cid]

    # Mock network
    mock_network = MagicMock()
    mock_network.containers = []
    mock_client._client.networks.get.return_value = mock_network

    state = FactoryState()
    state.resolver = ResolverRecord(
        container_id="res-1",
        db_container_id="res-db-1",
        external_url="", internal_url="", status="RUNNING", started_at=datetime.now(UTC)
    )
    await state.add_platform(PlatformRecord(
        platform_id="p1", stack="s1", issuer_id="i1", subject_types=[],
        container_id="plat-1", db_container_id="db-1",
        external_url="", internal_url="", status=PlatformStatus.RUNNING, created_at=datetime.now(UTC)
    ))

    await shutdown(mock_client, state)

    assert mock_client.stop_container.call_count == 4
    mock_network.remove.assert_called_once()

@pytest.mark.asyncio
async def test_shutdown_skipped_via_env():
    with patch("os.getenv", return_value="true"):
        mock_client = MagicMock()
        state = FactoryState()
        await shutdown(mock_client, state)
        mock_client.stop_container.assert_not_called()

@pytest.mark.asyncio
async def test_shutdown_network_busy(mocker):
    mock_client = MagicMock()
    # Mock empty containers list for get
    mock_client._client.containers.get.side_effect = Exception("Not found")

    # Mock network with containers
    mock_network = MagicMock()
    mock_network.containers = [MagicMock()]
    mock_client._client.networks.get.return_value = mock_network

    state = FactoryState()
    await shutdown(mock_client, state)

    mock_network.remove.assert_not_called()
