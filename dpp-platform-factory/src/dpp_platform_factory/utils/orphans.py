import os
import sys
import structlog
from docker.models.containers import Container
from ..infrastructure.docker_client import DockerClient, MANAGED_BY_LABEL
from ..core.state import FactoryState, ResolverRecord, PlatformRecord, PlatformStatus
from datetime import datetime, UTC

logger = structlog.get_logger()

ORPHAN_ENV_VAR = "DPP_FACTORY_ORPHANS"

def find_orphans(client: DockerClient) -> list[Container]:
    """Find all containers managed by dpp-factory."""
    return client.find_containers_by_label({"managed-by": "dpp-factory"})

def prompt_orphan_action() -> str:
    """Determine action for orphaned containers: shutdown, reuse, or fail."""
    env_val = os.getenv(ORPHAN_ENV_VAR)
    if env_val:
        if env_val in ("shutdown", "reuse", "fail"):
            logger.info("orphan_action_from_env", action=env_val)
            return env_val
        else:
            logger.warning("invalid_orphan_env_value", value=env_val)

    if not sys.stdin.isatty():
        logger.error("non_interactive_orphans_found", 
                     message="Orphaned containers found but no TTY and no DPP_FACTORY_ORPHANS env var.")
        return "fail"

    print("\nOrphaned DPP containers detected. Choose action:")
    print("  [s]hutdown - Stop and remove all orphaned containers")
    print("  [r]euse    - Attempt to reconstruct state and continue")
    print("  [f]ail     - Abort startup (default)")
    
    try:
        choice = input("Choice [s/r/f]: ").strip().lower()
        if choice == 's': return "shutdown"
        if choice == 'r': return "reuse"
        return "fail"
    except EOFError:
        return "fail"

async def shutdown_orphans(client: DockerClient, containers: list[Container]) -> None:
    """Stop and remove orphaned containers."""
    for container in containers:
        logger.info("orphan_shutdown", name=container.name)
        client.stop_container(container)
        client.remove_container(container)

async def reuse_orphans(client: DockerClient, containers: list[Container]) -> FactoryState:
    """Reconstruct FactoryState from container labels and inspect data."""
    state = FactoryState()
    
    # Sort containers: resolver first, then platforms
    resolver_cont = None
    resolver_db_cont = None
    platform_conts = {} # platform_id -> {role: container}
    
    for container in containers:
        labels = container.labels
        role = labels.get("dpp-factory-role")
        platform_id = labels.get("dpp-factory-platform-id")
        
        if role == "resolver":
            resolver_cont = container
        elif role == "resolver-db":
            resolver_db_cont = container
        elif platform_id:
            if platform_id not in platform_conts:
                platform_conts[platform_id] = {}
            platform_conts[platform_id][role] = container

    if resolver_cont:
        # Reconstruct ResolverRecord
        # We need to find the host port if any.
        ports = resolver_cont.attrs.get("NetworkSettings", {}).get("Ports", {})
        # Assuming 8080/tcp is the internal port
        port_mappings = ports.get("8080/tcp")
        external_url = ""
        if port_mappings:
            host_port = port_mappings[0].get("HostPort")
            external_url = f"http://localhost:{host_port}"
            
        record = ResolverRecord(
            container_id=resolver_cont.id,
            db_container_id=resolver_db_cont.id if resolver_db_cont else "",
            external_url=external_url,
            internal_url=f"http://{resolver_cont.name}:8080",
            status="RUNNING" if resolver_cont.status == "running" else "PAUSED",
            started_at=datetime.now(UTC) # Best effort
        )
        await state.set_resolver(record)

    for pid, roles in platform_conts.items():
        cont = roles.get("platform")
        db_cont = roles.get("database")
        if not cont: continue
        
        labels = cont.labels
        ports = cont.attrs.get("NetworkSettings", {}).get("Ports", {})
        port_mappings = ports.get("8080/tcp")
        external_url = ""
        if port_mappings:
            host_port = port_mappings[0].get("HostPort")
            external_url = f"http://localhost:{host_port}"

        record = PlatformRecord(
            platform_id=pid,
            stack=labels.get("dpp-stack", "unknown"),
            issuer_id=labels.get("dpp-issuer-id", "unknown"),
            subject_types=labels.get("dpp-subject-types", "").split(","),
            container_id=cont.id,
            db_container_id=db_cont.id if db_cont else "",
            external_url=external_url,
            internal_url=f"http://{cont.name}:8080",
            status=PlatformStatus.RUNNING if cont.status == "running" else PlatformStatus.PAUSED,
            created_at=datetime.now(UTC) # Best effort
        )
        await state.add_platform(record)
        
    return state

async def handle_orphans(client: DockerClient, state: FactoryState) -> FactoryState:
    """Detect and handle orphans, possibly updating the provided state."""
    orphans = find_orphans(client)
    if not orphans:
        return state
        
    logger.info("orphans_detected", count=len(orphans))
    action = prompt_orphan_action()
    
    if action == "shutdown":
        await shutdown_orphans(client, orphans)
    elif action == "reuse":
        reused_state = await reuse_orphans(client, orphans)
        # Merge reused_state into state
        if reused_state.resolver:
            await state.set_resolver(reused_state.resolver)
        for pid, record in reused_state.platforms.items():
            await state.add_platform(record)
    else:
        raise RuntimeError("Startup aborted due to orphaned containers.")
        
    return state
