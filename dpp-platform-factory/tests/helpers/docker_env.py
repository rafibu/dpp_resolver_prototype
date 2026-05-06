import docker
import docker.errors
import structlog

logger = structlog.get_logger()

REQUIRED_IMAGES = [
    "dpp-resolver:latest",
    "dpp-platform-spring:latest",
    "dpp-platform-fastapi:latest",
]

def is_docker_available() -> bool:
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False

def has_required_images() -> bool:
    if not is_docker_available():
        return False
    client = docker.from_env()
    for image in REQUIRED_IMAGES:
        try:
            client.images.get(image)
        except docker.errors.ImageNotFound:
            logger.warning("missing_required_image", image=image)
            return False
    return True

def cleanup_factory_containers():
    if not is_docker_available():
        return
    client = docker.from_env()
    # Find containers with managed-by=dpp-factory label
    containers = client.containers.list(all=True, filters={"label": "managed-by=dpp-factory"})
    for container in containers:
        try:
            logger.info("cleanup_removing_container", name=container.name)
            container.stop(timeout=1)
            container.remove(v=True, force=True)
        except Exception as exc:
            logger.warning("cleanup_failed", name=container.name, error=str(exc))

    # Also cleanup dpp-net if it exists and is empty
    try:
        net = client.networks.get("dpp-net")
        if not net.containers:
             net.remove()
             logger.info("cleanup_removed_network", name="dpp-net")
    except docker.errors.NotFound:
        pass
    except Exception as exc:
        logger.warning("cleanup_network_failed", error=str(exc))
