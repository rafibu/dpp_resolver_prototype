import docker.errors
import httpx
import pytest
from unittest.mock import MagicMock, call, patch

from dpp_platform_factory.infrastructure.docker_client import MANAGED_BY_LABEL, DockerClient, _LABEL_KEY, _LABEL_VALUE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sdk() -> MagicMock:
    """A fully mocked docker.DockerClient SDK instance."""
    return MagicMock()


@pytest.fixture
def client(sdk: MagicMock) -> DockerClient:
    """DockerClient under test with an injected mock SDK."""
    return DockerClient(client=sdk)


def _mock_container(name: str = "test-container") -> MagicMock:
    c = MagicMock()
    c.name = name
    c.short_id = "abc123"
    return c


def _mock_network(name: str = "dpp-net") -> MagicMock:
    n = MagicMock()
    n.name = name
    n.short_id = "net456"
    return n


# ---------------------------------------------------------------------------
# MANAGED_BY_LABEL constant
# ---------------------------------------------------------------------------


def test_managed_by_label_format():
    assert "=" in MANAGED_BY_LABEL
    key, value = MANAGED_BY_LABEL.split("=", 1)
    assert key == "managed-by"
    assert value == "dpp-factory"


def test_label_key_value_parsed_correctly():
    assert _LABEL_KEY == "managed-by"
    assert _LABEL_VALUE == "dpp-factory"


# ---------------------------------------------------------------------------
# ensure_network
# ---------------------------------------------------------------------------


def test_ensure_network_returns_existing(client: DockerClient, sdk: MagicMock):
    existing = _mock_network("dpp-net")
    sdk.networks.get.return_value = existing

    result = client.ensure_network("dpp-net")

    sdk.networks.get.assert_called_once_with("dpp-net")
    sdk.networks.create.assert_not_called()
    assert result is existing


def test_ensure_network_creates_when_not_found(client: DockerClient, sdk: MagicMock):
    sdk.networks.get.side_effect = docker.errors.NotFound("not found")
    created = _mock_network("dpp-net")
    sdk.networks.create.return_value = created

    result = client.ensure_network("dpp-net")

    sdk.networks.create.assert_called_once_with("dpp-net", driver="bridge")
    assert result is created


def test_ensure_network_does_not_create_if_exists(client: DockerClient, sdk: MagicMock):
    sdk.networks.get.return_value = _mock_network()

    client.ensure_network("dpp-net")

    sdk.networks.create.assert_not_called()


# ---------------------------------------------------------------------------
# find_containers_by_label
# ---------------------------------------------------------------------------


def test_find_containers_by_label_passes_correct_filter(client: DockerClient, sdk: MagicMock):
    sdk.containers.list.return_value = []

    client.find_containers_by_label({"managed-by": "dpp-factory", "platform-id": "p-a"})

    sdk.containers.list.assert_called_once()
    call_kwargs = sdk.containers.list.call_args[1]
    assert call_kwargs["all"] is True
    label_filter = call_kwargs["filters"]["label"]
    assert "managed-by=dpp-factory" in label_filter
    assert "platform-id=p-a" in label_filter


def test_find_containers_by_label_returns_list(client: DockerClient, sdk: MagicMock):
    containers = [_mock_container("c1"), _mock_container("c2")]
    sdk.containers.list.return_value = containers

    result = client.find_containers_by_label({"managed-by": "dpp-factory"})

    assert result == containers


def test_find_containers_by_label_empty_result(client: DockerClient, sdk: MagicMock):
    sdk.containers.list.return_value = []

    result = client.find_containers_by_label({"managed-by": "dpp-factory"})

    assert result == []


# ---------------------------------------------------------------------------
# run_container
# ---------------------------------------------------------------------------


def test_run_container_delegates_to_sdk(client: DockerClient, sdk: MagicMock):
    container = _mock_container("platform-b")
    sdk.containers.run.return_value = container

    result = client.run_container(
        image="dpp-platform-python:latest",
        name="platform-b",
        env={"PLATFORM_ID": "platform-b"},
        ports={"8082/tcp": 8082},
        volumes={"mongo-b": {"bind": "/data/db", "mode": "rw"}},
        network="dpp-net",
        labels={"platform-id": "platform-b"},
    )

    sdk.containers.run.assert_called_once()
    assert result is container


def test_run_container_always_includes_managed_by_label(client: DockerClient, sdk: MagicMock):
    sdk.containers.run.return_value = _mock_container()

    client.run_container(
        image="img",
        name="c",
        env={},
        ports={},
        volumes={},
        network="net",
        labels={"custom": "value"},
    )

    call_kwargs = sdk.containers.run.call_args[1]
    assert call_kwargs["labels"][_LABEL_KEY] == _LABEL_VALUE


def test_run_container_caller_labels_preserved(client: DockerClient, sdk: MagicMock):
    sdk.containers.run.return_value = _mock_container()

    client.run_container(
        image="img",
        name="c",
        env={},
        ports={},
        volumes={},
        network="net",
        labels={"platform-id": "my-platform"},
    )

    call_kwargs = sdk.containers.run.call_args[1]
    assert call_kwargs["labels"]["platform-id"] == "my-platform"


def test_run_container_detach_true(client: DockerClient, sdk: MagicMock):
    sdk.containers.run.return_value = _mock_container()

    client.run_container(
        image="img", name="c", env={}, ports={}, volumes={}, network="net", labels={}
    )

    call_kwargs = sdk.containers.run.call_args[1]
    assert call_kwargs["detach"] is True
    assert call_kwargs["remove"] is False


# ---------------------------------------------------------------------------
# stop_container
# ---------------------------------------------------------------------------


def test_stop_container_calls_stop(client: DockerClient):
    container = _mock_container()

    client.stop_container(container, timeout=15)

    container.stop.assert_called_once_with(timeout=15)


def test_stop_container_default_timeout(client: DockerClient):
    container = _mock_container()

    client.stop_container(container)

    container.stop.assert_called_once_with(timeout=10)


# ---------------------------------------------------------------------------
# remove_container
# ---------------------------------------------------------------------------


def test_remove_container_calls_remove(client: DockerClient):
    container = _mock_container()

    client.remove_container(container)

    container.remove.assert_called_once_with(v=False)


def test_remove_container_with_volumes(client: DockerClient):
    container = _mock_container()

    client.remove_container(container, remove_volumes=True)

    container.remove.assert_called_once_with(v=True)


def test_remove_volume_removes_existing_named_volume(client: DockerClient, sdk: MagicMock):
    volume = MagicMock()
    sdk.volumes.get.return_value = volume

    removed = client.remove_volume("dpp-resolver-db-data")

    assert removed is True
    sdk.volumes.get.assert_called_once_with("dpp-resolver-db-data")
    volume.remove.assert_called_once_with(force=True)


def test_remove_volume_ignores_missing_named_volume(client: DockerClient, sdk: MagicMock):
    sdk.volumes.get.side_effect = docker.errors.NotFound("missing")

    removed = client.remove_volume("dpp-resolver-db-data")

    assert removed is False


# ---------------------------------------------------------------------------
# start_container
# ---------------------------------------------------------------------------


def test_start_container_calls_start(client: DockerClient):
    container = _mock_container()

    client.start_container(container)

    container.start.assert_called_once()


# ---------------------------------------------------------------------------
# wait_healthy
# ---------------------------------------------------------------------------


def test_wait_healthy_succeeds_on_first_attempt(client: DockerClient):
    container = _mock_container()
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("dpp_platform_factory.infrastructure.docker_client.httpx.get", return_value=mock_response) as mock_get:
        client.wait_healthy(container, "http://localhost:8082/health", timeout=10)

    mock_get.assert_called_once_with("http://localhost:8082/health", timeout=2.0)


def test_wait_healthy_retries_until_200(client: DockerClient):
    container = _mock_container()

    fail = MagicMock()
    fail.status_code = 503
    success = MagicMock()
    success.status_code = 200

    with patch("dpp_platform_factory.infrastructure.docker_client.httpx.get", side_effect=[fail, fail, success]):
        with patch("dpp_platform_factory.infrastructure.docker_client.time.sleep"):
            client.wait_healthy(container, "http://localhost:8082/health", timeout=30)


def test_wait_healthy_raises_timeout_on_connection_error(client: DockerClient):
    container = _mock_container()

    with patch(
        "dpp_platform_factory.infrastructure.docker_client.httpx.get",
        side_effect=httpx.ConnectError("refused"),
    ):
        with patch("dpp_platform_factory.infrastructure.docker_client.time.sleep"):
            with patch("dpp_platform_factory.infrastructure.docker_client.time.monotonic", side_effect=[0, 0, 2]):
                with pytest.raises(TimeoutError, match="platform-b" if False else "test-container"):
                    client.wait_healthy(
                        container, "http://localhost:8082/health", timeout=1
                    )


def test_wait_healthy_timeout_error_message_contains_url(client: DockerClient):
    container = _mock_container("my-platform")

    with patch("dpp_platform_factory.infrastructure.docker_client.httpx.get", side_effect=ConnectionError("refused")):
        with patch("dpp_platform_factory.infrastructure.docker_client.time.sleep"):
            with patch("dpp_platform_factory.infrastructure.docker_client.time.monotonic", side_effect=[0, 0, 99]):
                with pytest.raises(TimeoutError) as exc_info:
                    client.wait_healthy(container, "http://localhost:9999/health", timeout=1)

    assert "http://localhost:9999/health" in str(exc_info.value)
    assert "my-platform" in str(exc_info.value)


def test_wait_healthy_non_200_then_200(client: DockerClient):
    container = _mock_container()
    responses = [
        MagicMock(status_code=404),
        MagicMock(status_code=503),
        MagicMock(status_code=200),
    ]

    with patch("dpp_platform_factory.infrastructure.docker_client.httpx.get", side_effect=responses):
        with patch("dpp_platform_factory.infrastructure.docker_client.time.sleep"):
            client.wait_healthy(container, "http://localhost:8082/health", timeout=30)


def test_wait_healthy_passes_correct_url(client: DockerClient):
    container = _mock_container()
    mock_response = MagicMock(status_code=200)

    with patch("dpp_platform_factory.infrastructure.docker_client.httpx.get", return_value=mock_response) as mock_get:
        client.wait_healthy(container, "http://platform-b:8082/health")

    mock_get.assert_called_with("http://platform-b:8082/health", timeout=2.0)


# ---------------------------------------------------------------------------
# Constructor: default path uses docker.from_env()
# ---------------------------------------------------------------------------


def test_default_constructor_calls_from_env():
    with patch("dpp_platform_factory.infrastructure.docker_client.docker.from_env") as mock_from_env:
        mock_from_env.return_value = MagicMock()
        dc = DockerClient()
        mock_from_env.assert_called_once()


def test_injected_client_skips_from_env():
    mock_sdk = MagicMock()
    with patch("dpp_platform_factory.infrastructure.docker_client.docker.from_env") as mock_from_env:
        DockerClient(client=mock_sdk)
        mock_from_env.assert_not_called()
