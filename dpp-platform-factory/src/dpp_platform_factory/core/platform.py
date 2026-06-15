"""
Container lifecycle for DPP platform instances.

Each spawned platform is a running instance of either the Java/Postgres or Python/MongoDB
platform implementation. Both implement the same REST contract, modelling a DPP platform
state (Definition 5): a set of revisions and a local schema cache. The factory starts them
with the correct environment variables (RESOLVER_URL, ISSUER_ID, SUBJECT_TYPES) so they
can connect to the shared Resolver and satisfy Invariants I3 and I7 at issuance time.

Container names and Docker labels are the sole persistence mechanism: on restart the
factory can recover the running topology from Docker's label index without a database.
"""
import asyncio
import structlog
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from .state import PlatformRecord, PlatformStatus
from ..infrastructure.docker_client import DockerClient

logger = structlog.get_logger()

PLATFORM_INTERNAL_PORT = 8080

_DB_IMAGES: dict[str, str] = {
    "spring-postgres": "postgres:16",
    "fastapi-mongo": "mongo:7",
}
_PLATFORM_IMAGES: dict[str, str] = {
    "spring-postgres": "generic-dpp-platform-java:latest",
    "fastapi-mongo": "generic-dpp-platform-python:latest",
}


@dataclass
class PlatformSpec:
    platform_id: str
    stack: str
    issuer_id: str
    subject_types: list[str]
    host_port: int


async def spawn_platform(
        client: DockerClient,
        network_name: str,
        resolver_url: str,
        spec: PlatformSpec,
) -> PlatformRecord:
    logger.info("platform_spawning", platform_id=spec.platform_id, stack=spec.stack)

    db_name = f"dpp-{spec.platform_id}-db"
    container_name = f"dpp-{spec.platform_id}"
    db_labels = _db_labels(spec.platform_id)
    platform_labels = _platform_labels(spec.platform_id, spec.stack, spec.issuer_id, spec.subject_types, spec.host_port)
    db_volume = platform_db_volume_name(spec.platform_id)

    db_container = None
    platform_container = None
    try:
        db_env, db_mount = _db_env_and_mount(spec.stack)
        db_container = client.run_container(
            image=_DB_IMAGES[spec.stack],
            name=db_name,
            env=db_env,
            ports={},
            volumes={db_volume: {"bind": db_mount, "mode": "rw"}},
            network=network_name,
            labels=db_labels,
            command=_db_command(spec.stack),
        )
        await _wait_db_ready(db_container, spec.stack, timeout=60)

        external_url = f"http://localhost:{spec.host_port}"
        platform_container = client.run_container(
            image=_PLATFORM_IMAGES[spec.stack],
            name=container_name,
            env={
                "PLATFORM_ID": spec.platform_id,
                "PLATFORM_NAME": spec.platform_id,
                "ISSUER_ID": spec.issuer_id,
                "SUBJECT_TYPES": ",".join(spec.subject_types),
                "RESOLVER_URL": resolver_url,
                "RESOLVER_BASE_URL": resolver_url,
                "BASE_URL": external_url,
                "DATABASE_URL": _database_url(spec.stack, db_name),
                "LOG_LEVEL": "INFO",
            },
            ports={f"{PLATFORM_INTERNAL_PORT}/tcp": spec.host_port},
            volumes={},
            network=network_name,
            labels=platform_labels,
        )

        internal_url = f"http://{container_name}:{PLATFORM_INTERNAL_PORT}"
        client.wait_healthy(platform_container, f"{internal_url}/health", timeout=30)

        logger.info("platform_spawned", platform_id=spec.platform_id, external_url=external_url)

        return PlatformRecord(
            platform_id=spec.platform_id,
            stack=spec.stack,
            issuer_id=spec.issuer_id,
            subject_types=spec.subject_types,
            container_id=platform_container.id,
            db_container_id=db_container.id,
            external_url=external_url,
            internal_url=internal_url,
            status=PlatformStatus.RUNNING,
            created_at=datetime.now(UTC),
        )

    except Exception:
        logger.exception("platform_spawn_failed", platform_id=spec.platform_id)
        _cleanup_partial(client, platform_container, db_container)
        raise


async def teardown_platform(client: DockerClient, record: PlatformRecord) -> None:
    logger.info("platform_tearing_down", platform_id=record.platform_id)
    for cid in [record.container_id, record.db_container_id]:
        _stop_by_id(client, cid, remove_volumes=True)
    logger.info("platform_torn_down", platform_id=record.platform_id)


async def rebuild_db(client: DockerClient, record: PlatformRecord, network_name: str) -> str:
    """Stop and remove database container + volume, then spawn a fresh one. Returns new container ID."""
    db_name = f"dpp-{record.platform_id}-db"
    db_volume = platform_db_volume_name(record.platform_id)
    _stop_by_id(client, record.db_container_id, remove_volumes=True)
    client.remove_volume(db_volume)

    db_env, db_mount = _db_env_and_mount(record.stack)
    db_container = client.run_container(
        image=_DB_IMAGES[record.stack],
        name=db_name,
        env=db_env,
        ports={},
        volumes={db_volume: {"bind": db_mount, "mode": "rw"}},
        network=network_name,
        labels=_db_labels(record.platform_id),
        command=_db_command(record.stack),
    )
    await _wait_db_ready(db_container, record.stack, timeout=60)
    return db_container.id


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------


def _db_env_and_mount(stack: str) -> tuple[dict[str, str], str]:
    if stack == "spring-postgres":
        return (
            {"POSTGRES_DB": "dpp_platform", "POSTGRES_USER": "postgres", "POSTGRES_PASSWORD": "postgres"},
            "/var/lib/postgresql/data",
        )
    return {}, "/data/db"


def _db_command(stack: str) -> list[str] | None:
    if stack == "fastapi-mongo":
        # --replSet rs0 enables multi-document transactions required by the Python platform.
        # Without it, PyMongo raises "Transaction numbers are only allowed on a replica set member".
        return ["mongod", "--replSet", "rs0", "--bind_ip_all"]
    return None


def _database_url(stack: str, db_name: str) -> str:
    if stack == "spring-postgres":
        return f"jdbc:postgresql://{db_name}:5432/dpp_platform"
    # replicaSet=rs0 is required: without it PyMongo connects in standalone mode
    # and raises "Transaction numbers are only allowed on a replica set member".
    return f"mongodb://{db_name}:27017/?replicaSet=rs0"


def platform_db_volume_name(platform_id: str) -> str:
    return f"dpp-{platform_id}-db-data"


def _db_labels(platform_id: str) -> dict[str, str]:
    return {
        "managed-by": "dpp-factory",
        "dpp-factory-role": "database",
        "dpp-factory-platform-id": platform_id,
    }


def _platform_labels(
        platform_id: str,
        stack: str,
        issuer_id: str,
        subject_types: list[str],
        host_port: int,
) -> dict[str, str]:
    return {
        "managed-by": "dpp-factory",
        "dpp-factory-role": "platform",
        "dpp-factory-platform-id": platform_id,
        "dpp-factory-stack": stack,
        "dpp-factory-issuer-id": issuer_id,
        "dpp-factory-subject-types": ",".join(subject_types),
        "dpp-factory-host-port": str(host_port),
    }


def _cleanup_partial(client: DockerClient, *containers) -> None:
    for c in containers:
        if c is None:
            continue
        try:
            client.stop_container(c, timeout=5)
            client.remove_container(c, remove_volumes=True)
        except Exception as exc:
            logger.warning("cleanup_failed", container=c.name, error=str(exc))


def _stop_by_id(client: DockerClient, container_id: str, remove_volumes: bool = False) -> None:
    try:
        client.stop_and_remove_by_id(container_id, remove_volumes=remove_volumes)
    except Exception as exc:
        logger.warning("container_stop_failed", container_id=container_id, error=str(exc))


async def _wait_db_ready(container, stack: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if stack == "spring-postgres":
                code, _ = container.exec_run(["pg_isready", "-U", "postgres"], demux=False)
            else:
                code, _ = container.exec_run(
                    ["mongosh", "--eval", "db.adminCommand({ping:1})"], demux=False
                )
            if code == 0:
                logger.info("db_ready", container=container.name, stack=stack)
                if stack == "fastapi-mongo":
                    await _init_mongo_replset(container)
                return
        except Exception:
            pass
        await asyncio.sleep(1)
    raise TimeoutError(f"Database '{container.name}' did not become ready within {timeout}s")


async def _init_mongo_replset(container, timeout: int = 30) -> None:
    """Initiate single-node replica set and wait for primary election.

    Required because MongoDB standalone instances do not support multi-document
    transactions. rs.initiate() is skipped if already done (idempotent).

    The replica set member must be configured with the container name (not 'localhost')
    because platform containers reach MongoDB over the Docker network using that name.
    Using 'localhost' causes ServerSelectionTimeoutError from other containers.
    """
    host = f"{container.name}:27017"
    # Try rs.initiate() first (fresh DB). If already initiated (stale volume),
    # force-reconfig to ensure the correct container-name hostname is used.
    # Using 'localhost' would cause ServerSelectionTimeoutError from other containers.
    init_js = (
        f"var h = '{host}'; "
        f"try {{ "
        f"  rs.initiate({{_id:'rs0', members:[{{_id:0, host:h}}]}}); "
        f"  print('initiated'); "
        f"}} catch(e) {{ "
        f"  var c = rs.conf(); "
        f"  c.members[0].host = h; "
        f"  c.version = c.version + 1; "
        f"  rs.reconfig(c, {{force:true}}); "
        f"  print('reconfigured'); "
        f"}}"
    )
    code, _ = container.exec_run(["mongosh", "--eval", init_js], demux=False)
    if code != 0:
        logger.warning("mongo_replset_init_failed", container=container.name)
        return

    # Wait until this node becomes primary before handing back to the caller.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, out = container.exec_run(
            ["mongosh", "--quiet", "--eval", "db.adminCommand({isMaster:1}).ismaster"],
            demux=False,
        )
        if code == 0 and b"true" in out:
            logger.info("mongo_replset_primary_elected", container=container.name)
            return
        await asyncio.sleep(1)
    logger.warning("mongo_replset_primary_not_elected", container=container.name)
