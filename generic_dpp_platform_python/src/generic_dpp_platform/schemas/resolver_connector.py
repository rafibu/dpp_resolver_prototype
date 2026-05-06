import structlog
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..admin import service as admin_service
from . import service as schema_service
from .models import DppSchemaDTO

logger = structlog.get_logger()


async def sync_schema(db: AsyncIOMotorDatabase, subject_type: str) -> None:
    config = await admin_service.get_platform_config(db)
    resolver_base_url = config.resolver_base_url

    if not resolver_base_url:
        raise ValueError("Resolver base URL is not configured")

    if not await db.subject_types.find_one({"name": subject_type}):
        raise ValueError(f"Subject type not found: {subject_type}")

    url = f"{resolver_base_url}/schemas/{subject_type}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        remote_schemas_raw: list[dict] = response.json()

    remote_schemas = [DppSchemaDTO(**s) for s in remote_schemas_raw]
    saved = await schema_service.save_schemas(db, remote_schemas)
    logger.info("schema_sync_complete", subject_type=subject_type, new_schemas=saved)


async def resolve_dpp_revision(
    db: AsyncIOMotorDatabase,
    subject_type: str,
    dpp_id: str,
    version: int | None,
) -> "DppRevisionResponseDTO | None":
    """Resolve a DPP revision via the Resolver (follows 302 redirect to hosting platform)."""
    from ..dpps.exceptions import DppReferenceResolutionException
    from ..dpps.models import DppRevisionResponseDTO

    if version is None:
        raise DppReferenceResolutionException(f"{subject_type}/{dpp_id}")

    config = await admin_service.get_platform_config(db)
    resolver_base_url = config.resolver_base_url
    if not resolver_base_url:
        raise DppReferenceResolutionException(f"{subject_type}/{dpp_id}/{version}")

    url = f"{resolver_base_url}/{subject_type}/{dpp_id}/{version}"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url)
        if response.status_code == 404:
            raise DppReferenceResolutionException(f"{subject_type}/{dpp_id}/{version}")
        response.raise_for_status()
        return DppRevisionResponseDTO(**response.json())
    except DppReferenceResolutionException:
        raise
    except Exception as exc:
        raise DppReferenceResolutionException(f"{subject_type}/{dpp_id}/{version}") from exc
