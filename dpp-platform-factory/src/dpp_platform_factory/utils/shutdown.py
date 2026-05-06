import os
import asyncio
import structlog
import docker.errors
from ..infrastructure.docker_client import DockerClient, DPP_NET
from ..core.state import FactoryState

logger = structlog.get_logger()

KEEP_RUNNING_ENV_VAR = "DPP_FACTORY_KEEP_RUNNING"

async def shutdown(client: DockerClient, state: FactoryState) -> None:
    """Gracefully stop all managed containers in the correct order."""
    if os.getenv(KEEP_RUNNING_ENV_VAR, "").lower() == "true":
        logger.info("shutdown_skipped", reason="DPP_FACTORY_KEEP_RUNNING is true")
        return

    logger.info("shutdown_started")

    # 1. Stop all platform containers in parallel
    platform_records = list(state.platforms.values())
    
    async def stop_platform(record):
        try:
            container = client._client.containers.get(record.container_id)
            client.stop_container(container)
        except docker.errors.NotFound:
            pass
        except Exception as exc:
            logger.warning("shutdown_platform_failed", platform_id=record.platform_id, error=str(exc))

    if platform_records:
        logger.info("shutdown_platforms", count=len(platform_records))
        await asyncio.gather(*(stop_platform(p) for p in platform_records))

    # 2. Stop all platform database containers in parallel
    async def stop_db(record):
        if not record.db_container_id: return
        try:
            container = client._client.containers.get(record.db_container_id)
            client.stop_container(container)
        except docker.errors.NotFound:
            pass
        except Exception as exc:
            logger.warning("shutdown_db_failed", db_id=record.db_container_id, error=str(exc))

    if platform_records:
        logger.info("shutdown_platform_databases")
        await asyncio.gather(*(stop_db(p) for p in platform_records))

    # 3. Stop Resolver container
    if state.resolver:
        logger.info("shutdown_resolver")
        try:
            container = client._client.containers.get(state.resolver.container_id)
            client.stop_container(container)
        except docker.errors.NotFound:
            pass
        except Exception as exc:
            logger.warning("shutdown_resolver_failed", error=str(exc))

        # 4. Stop Resolver database container
        if state.resolver.db_container_id:
            logger.info("shutdown_resolver_db")
            try:
                container = client._client.containers.get(state.resolver.db_container_id)
                client.stop_container(container)
            except docker.errors.NotFound:
                pass
            except Exception as exc:
                logger.warning("shutdown_resolver_db_failed", error=str(exc))

    # 5. Remove dpp-net network if no other containers are using it
    try:
        network = client._client.networks.get(DPP_NET)
        # Check if any containers are still attached
        if not network.containers:
            logger.info("shutdown_removing_network", network=DPP_NET)
            network.remove()
        else:
            logger.info("shutdown_keeping_network", network=DPP_NET, 
                        containers=[c.name for c in network.containers])
    except docker.errors.NotFound:
        pass
    except Exception as exc:
        logger.warning("shutdown_network_removal_failed", error=str(exc))

    logger.info("shutdown_complete")
