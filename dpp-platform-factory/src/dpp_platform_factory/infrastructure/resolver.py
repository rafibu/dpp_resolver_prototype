import asyncio
import structlog
import time
from datetime import UTC, datetime

from .docker_client import DockerClient
from ..core.state import PlatformStatus, ResolverRecord
from ..utils.config import ResolverConfig

logger = structlog.get_logger()

RESOLVER_NAME = "dpp-resolver"
RESOLVER_DB_NAME = "dpp-resolver-db"
RESOLVER_DB_VOLUME = f"{RESOLVER_DB_NAME}-data"
RESOLVER_IMAGE = "dpp-resolver:latest"
RESOLVER_DB_IMAGE = "postgres:16"
RESOLVER_INTERNAL_PORT = 8080

_BASE_LABELS = {"managed-by": "dpp-factory"}
_RESOLVER_LABELS = {**_BASE_LABELS, "dpp-factory-role": "resolver"}
_RESOLVER_DB_LABELS = {**_BASE_LABELS, "dpp-factory-role": "resolver-db"}


async def start_resolver(
    client: DockerClient,
    network_name: str,
    config: ResolverConfig,
) -> ResolverRecord:
    logger.info("resolver_starting", port=config.port)

    db_container = client.run_container(
        image=RESOLVER_DB_IMAGE,
        name=RESOLVER_DB_NAME,
        env={
            "POSTGRES_DB": "dpp_resolver",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "postgres",
        },
        ports={},
        volumes={RESOLVER_DB_VOLUME: {"bind": "/var/lib/postgresql/data", "mode": "rw"}},
        network=network_name,
        labels=_RESOLVER_DB_LABELS,
    )

    await _wait_postgres_ready(db_container, timeout=60)

    resolver_container = client.run_container(
        image=RESOLVER_IMAGE,
        name=RESOLVER_NAME,
        env={
            "DATABASE_URL": f"jdbc:postgresql://{RESOLVER_DB_NAME}:5432/dpp_resolver",
            "DB_USERNAME": "postgres",
            "DB_PASSWORD": "postgres",
            "LOG_LEVEL": "INFO",
        },
        ports={f"{RESOLVER_INTERNAL_PORT}/tcp": config.port},
        volumes={},
        network=network_name,
        labels=_RESOLVER_LABELS,
    )

    external_url = f"http://localhost:{config.port}"
    internal_url = f"http://{RESOLVER_NAME}:{RESOLVER_INTERNAL_PORT}"
    client.wait_healthy(resolver_container, f"{internal_url}/health", timeout=60)

    logger.info("resolver_started", external_url=external_url)
    return ResolverRecord(
        container_id=resolver_container.id,
        db_container_id=db_container.id,
        external_url=external_url,
        internal_url=internal_url,
        status=PlatformStatus.RUNNING,
        started_at=datetime.now(UTC),
    )


async def stop_resolver(client: DockerClient, record: ResolverRecord) -> None:
    logger.info("resolver_stopping")
    for cid in [record.container_id, record.db_container_id]:
        _stop_by_id(client, cid)
    logger.info("resolver_stopped")


def _stop_by_id(client: DockerClient, container_id: str) -> None:
    try:
        container = client._client.containers.get(container_id)
        client.stop_container(container)
        client.remove_container(container)
    except Exception as exc:
        logger.warning("container_stop_failed", container_id=container_id, error=str(exc))


async def _wait_postgres_ready(container, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            exit_code, _ = container.exec_run(
                ["pg_isready", "-U", "postgres"], demux=False
            )
            if exit_code == 0:
                logger.info("postgres_ready", container=container.name)
                return
        except Exception:
            pass
        await asyncio.sleep(1)
    raise TimeoutError(
        f"Postgres '{container.name}' did not become ready within {timeout}s"
    )
