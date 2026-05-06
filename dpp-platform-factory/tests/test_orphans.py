import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from dpp_platform_factory.utils.orphans import find_orphans, prompt_orphan_action, shutdown_orphans, reuse_orphans, handle_orphans
from dpp_platform_factory.core.state import FactoryState, PlatformStatus

@pytest.fixture
def mock_client():
    return MagicMock()

def test_find_orphans(mock_client):
    mock_client.find_containers_by_label.return_value = ["cont1"]
    result = find_orphans(mock_client)
    assert result == ["cont1"]
    mock_client.find_containers_by_label.assert_called_once_with({"managed-by": "dpp-factory"})

@patch("os.getenv")
def test_prompt_orphan_action_env(mock_getenv):
    mock_getenv.return_value = "reuse"
    assert prompt_orphan_action() == "reuse"

@patch("sys.stdin.isatty")
def test_prompt_orphan_action_non_interactive(mock_isatty):
    mock_isatty.return_value = False
    with patch("os.getenv", return_value=None):
        assert prompt_orphan_action() == "fail"

@patch("sys.stdin.isatty")
@patch("builtins.input")
def test_prompt_orphan_action_interactive(mock_input, mock_isatty):
    mock_isatty.return_value = True
    mock_input.return_value = "s"
    assert prompt_orphan_action() == "shutdown"

@pytest.mark.asyncio
async def test_shutdown_orphans(mock_client):
    mock_cont = MagicMock()
    mock_cont.name = "orphan-1"
    await shutdown_orphans(mock_client, [mock_cont])
    mock_client.stop_container.assert_called_once_with(mock_cont)
    mock_client.remove_container.assert_called_once_with(mock_cont)

@pytest.mark.asyncio
async def test_reuse_orphans(mock_client):
    # Mock containers with labels
    mock_res = MagicMock()
    mock_res.id = "res-id"
    mock_res.name = "dpp-resolver"
    mock_res.status = "running"
    mock_res.labels = {"managed-by": "dpp-factory", "dpp-factory-role": "resolver"}
    mock_res.attrs = {"NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "8080"}]}}}

    mock_plat = MagicMock()
    mock_plat.id = "plat-id"
    mock_plat.name = "dpp-platform-a"
    mock_plat.status = "running"
    mock_plat.labels = {
        "managed-by": "dpp-factory",
        "dpp-factory-role": "platform",
        "dpp-factory-platform-id": "platform-a",
        "dpp-stack": "spring-postgres",
        "dpp-issuer-id": "issuer-a",
        "dpp-subject-types": "type-a,type-b"
    }
    mock_plat.attrs = {"NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "8081"}]}}}

    state = await reuse_orphans(mock_client, [mock_res, mock_plat])

    assert state.resolver.container_id == "res-id"
    assert state.resolver.external_url == "http://localhost:8080"
    assert "platform-a" in state.platforms
    assert state.platforms["platform-a"].stack == "spring-postgres"
    assert state.platforms["platform-a"].subject_types == ["type-a", "type-b"]
    assert state.platforms["platform-a"].external_url == "http://localhost:8081"

@pytest.mark.asyncio
async def test_handle_orphans_none(mock_client):
    mock_client.find_containers_by_label.return_value = []
    state = FactoryState()
    result = await handle_orphans(mock_client, state)
    assert result == state

@pytest.mark.asyncio
@patch("dpp_platform_factory.utils.orphans.prompt_orphan_action")
async def test_handle_orphans_shutdown(mock_prompt, mock_client):
    mock_cont = MagicMock()
    mock_client.find_containers_by_label.return_value = [mock_cont]
    mock_prompt.return_value = "shutdown"
    
    state = FactoryState()
    await handle_orphans(mock_client, state)
    
    mock_client.stop_container.assert_called_once()
    mock_client.remove_container.assert_called_once()
