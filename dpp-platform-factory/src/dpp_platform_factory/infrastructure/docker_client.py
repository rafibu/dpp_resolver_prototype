import time
from typing import Any

import docker
import docker.errors
import httpx
import structlog
from docker.models.containers import Container
from docker.models.networks import Network

logger = structlog.get_logger()

MANAGED_BY_LABEL = "managed-by=dpp-factory"
DPP_NET = "dpp-net"
_LABEL_KEY, _LABEL_VALUE = MANAGED_BY_LABEL.split("=", 1)


class DockerClient:
    """Thin wrapper over the Docker SDK scoped to Factory operations."""

    def __init__(self, client: docker.DockerClient | None = None) -> None:
        self._client: docker.DockerClient = client if client is not None else docker.from_env()

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def ensure_network(self, name: str) -> Network:
        """Return existing network or create it if absent."""
        try:
            network = self._client.networks.get(name)
            logger.info("docker_network_found", name=name, id=network.short_id)
            return network
        except docker.errors.NotFound:
            network = self._client.networks.create(name, driver="bridge")
            logger.info("docker_network_created", name=name, id=network.short_id)
            return network

    # ------------------------------------------------------------------
    # Container discovery
    # ------------------------------------------------------------------

    def find_containers_by_label(self, label_filters: dict[str, str]) -> list[Container]:
        """Return all containers (running or stopped) matching every label filter."""
        label_list = [f"{k}={v}" for k, v in label_filters.items()]
        containers: list[Container] = self._client.containers.list(
            all=True, filters={"label": label_list}
        )
        logger.info(
            "docker_containers_found",
            count=len(containers),
            labels=label_filters,
        )
        return containers

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def run_container(
        self,
        image: str,
        name: str,
        env: dict[str, str],
        ports: dict[str, Any],
        volumes: dict[str, Any],
        network: str,
        labels: dict[str, str],
    ) -> Container:
        """Create and start a container. Always attaches the MANAGED_BY_LABEL."""
        all_labels = {_LABEL_KEY: _LABEL_VALUE, **labels}
        logger.info("docker_container_starting", name=name, image=image)
        container: Container = self._client.containers.run(
            image=image,
            name=name,
            environment=env,
            ports=ports,
            volumes=volumes,
            network=network,
            labels=all_labels,
            detach=True,
            remove=False,
        )
        logger.info(
            "docker_container_started",
            name=name,
            container_id=container.short_id,
        )
        return container

    def stop_container(self, container: Container, timeout: int = 10) -> None:
        """Send SIGTERM and wait up to *timeout* seconds for the container to stop."""
        logger.info("docker_container_stopping", name=container.name, timeout=timeout)
        container.stop(timeout=timeout)
        logger.info("docker_container_stopped", name=container.name)

    def stop_by_id(self, container_id: str, timeout: int = 10) -> None:
        """Stop container by ID."""
        container = self.get_container(container_id)
        self.stop_container(container, timeout=timeout)

    def remove_container(self, container: Container, remove_volumes: bool = False) -> None:
        """Remove a stopped container, optionally purging its anonymous volumes."""
        logger.info(
            "docker_container_removing",
            name=container.name,
            remove_volumes=remove_volumes,
        )
        container.remove(v=remove_volumes)
        logger.info("docker_container_removed", name=container.name)

    def stop_and_remove_by_id(self, container_id: str, remove_volumes: bool = False) -> None:
        """Stop and remove container by ID."""
        try:
            container = self.get_container(container_id)
            self.stop_container(container)
            self.remove_container(container, remove_volumes=remove_volumes)
        except docker.errors.NotFound:
            logger.warning("docker_container_not_found_for_removal", container_id=container_id)

    def start_container(self, container: Container) -> None:
        """Start a previously stopped container."""
        logger.info("docker_container_resuming", name=container.name)
        container.start()
        logger.info("docker_container_resumed", name=container.name)

    def start_by_id(self, container_id: str) -> None:
        """Start container by ID."""
        container = self.get_container(container_id)
        self.start_container(container)

    def get_container(self, container_id: str) -> Container:
        """Retrieve a container by ID."""
        return self._client.containers.get(container_id)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def wait_healthy(
        self,
        container: Container,
        health_url: str,
        timeout: int = 30,
    ) -> None:
        """Poll *health_url* every second until HTTP 200 or *timeout* expires."""
        logger.info(
            "docker_waiting_healthy",
            name=container.name,
            url=health_url,
            timeout=timeout,
        )
        deadline = time.monotonic() + timeout
        last_exc: Exception | None = None

        while time.monotonic() < deadline:
            try:
                response = httpx.get(health_url, timeout=2.0)
                if response.status_code == 200:
                    logger.info("docker_container_healthy", name=container.name)
                    return
            except Exception as exc:
                last_exc = exc
            time.sleep(1)

        raise TimeoutError(
            f"Container '{container.name}' did not become healthy at {health_url} "
            f"within {timeout}s"
        ) from last_exc
