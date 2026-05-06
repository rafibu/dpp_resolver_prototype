import structlog

from .config import FederationConfig
from ..infrastructure.docker_client import DPP_NET, DockerClient
from .orphans import handle_orphans
from ..core.platform import PlatformSpec, spawn_platform
from ..infrastructure.resolver import start_resolver
from ..infrastructure.resolver_client import ResolverClient
from ..core.state import FactoryState, PlatformStatus

logger = structlog.get_logger()


async def bootstrap(
    client: DockerClient, config: FederationConfig, existing_state: FactoryState | None = None
) -> FactoryState:
    """Bring up the Resolver and all default-federation platforms. Returns populated FactoryState."""
    state = existing_state if existing_state is not None else FactoryState()

    # Detect orphaned containers from a previous run first
    await handle_orphans(client, state)

    # Ensure the Docker network exists
    network = client.ensure_network(DPP_NET)
    logger.info("bootstrap_network_ready", network=DPP_NET)

    # Start Resolver
    resolver_record = await start_resolver(client, network.name, config.resolver)
    await state.set_resolver(resolver_record)
    logger.info("bootstrap_resolver_ready", url=resolver_record.external_url)

    resolver_client = ResolverClient(resolver_record.internal_url)

    subject_types = sorted({
        subject_type
        for platform in config.platforms
        for subject_type in platform.subject_types
    })
    for subject_type in subject_types:
        await resolver_client.ensure_subject_type(subject_type)

    # Spawn default platforms sequentially (avoids port races; gives clean logs)
    for pconfig in config.platforms:
        try:
            spec = PlatformSpec(
                platform_id=pconfig.platform_id,
                stack=pconfig.stack,
                issuer_id=pconfig.issuer_id,
                subject_types=pconfig.subject_types,
                host_port=pconfig.port,
            )
            record = await spawn_platform(client, network.name, resolver_record.internal_url, spec)
            await resolver_client.register_platform(record)
            await state.add_platform(record)
            logger.info("bootstrap_platform_ready", platform_id=pconfig.platform_id)
        except Exception as exc:
            logger.error(
                "bootstrap_platform_failed",
                platform_id=pconfig.platform_id,
                error=str(exc),
            )
            # Mark as ERROR in state so the API can surface it; do not abort startup
            from ..core.state import PlatformRecord
            from datetime import UTC, datetime
            error_record = PlatformRecord(
                platform_id=pconfig.platform_id,
                stack=pconfig.stack,
                issuer_id=pconfig.issuer_id,
                subject_types=pconfig.subject_types,
                container_id="",
                db_container_id="",
                external_url=f"http://localhost:{pconfig.port}",
                internal_url="",
                status=PlatformStatus.ERROR,
                created_at=datetime.now(UTC),
            )
            await state.add_platform(error_record)

    return state
