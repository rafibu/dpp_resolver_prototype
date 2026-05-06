import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import Settings

logger = structlog.get_logger()

_client: AsyncIOMotorClient | None = None
_db_name: str = ""


async def get_database() -> AsyncIOMotorDatabase:
    global _client, _db_name
    if _client is not None:
        return _client[_db_name]

    from .config import get_settings
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _db_name = settings.mongodb_db_name
    db = _client[_db_name]

    await _setup_indexes(db)
    await _seed_platform_config(db, settings)
    logger.info("database_initialized", db_name=_db_name)
    return db


async def _setup_indexes(db: AsyncIOMotorDatabase) -> None:
    # Admin
    await db.subject_types.create_index("name", unique=True)

    # Schemas
    await db.schemas.create_index(
        [("subject_type", 1), ("major_version", 1), ("minor_version", 1)],
        unique=True,
    )

    # Logical DPPs
    await db.logical_dpps.create_index("dpp_id", unique=True)

    # DPP revisions: unique per (dpp_id, version), fast lookup by dpp_id + sort
    await db.dpp_revisions.create_index(
        [("dpp_id", 1), ("dpp_version", 1)],
        unique=True,
    )
    await db.dpp_revisions.create_index([("dpp_id", 1), ("dpp_version", -1)])

    # External cache: unique compound key + TTL on fetched_at (7 days)
    await db.referenced_dpp_revisions.create_index(
        [("dpp_id", 1), ("dpp_version", 1)],
        unique=True,
    )
    await db.referenced_dpp_revisions.create_index(
        "fetched_at",
        expireAfterSeconds=604800,  # 7 days
    )


async def _seed_platform_config(db: AsyncIOMotorDatabase, settings: Settings) -> None:
    count = await db.platform_config.count_documents({})
    if count == 0:
        await db.platform_config.insert_one(
            {
                "platform_name": settings.platform_name,
                "base_url": settings.base_url,
                "issuer_id": settings.issuer_id,
                "resolver_base_url": settings.resolver_base_url,
            }
        )
