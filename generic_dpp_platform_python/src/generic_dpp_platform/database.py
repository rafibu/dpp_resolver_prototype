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

    # Materialized predicate-query facts.  The unique key represents the one
    # current value per logical DPP/path invariant used by the Java platform.
    await db.query_attribute_fact.create_index(
        [("logical_dpp_id", 1), ("path", 1)],
        unique=True,
        name="uq_qaf_logical_dpp_path",
    )
    await db.query_attribute_fact.create_index(
        [("subject_type", 1), ("path", 1)], name="idx_qaf_subject_path"
    )
    await db.query_attribute_fact.create_index(
        [("subject_type", 1), ("path", 1), ("value_text", 1)], name="idx_qaf_text_lookup"
    )
    await db.query_attribute_fact.create_index(
        [("subject_type", 1), ("path", 1), ("value_number", 1)], name="idx_qaf_number_lookup"
    )
    await db.query_attribute_fact.create_index(
        [("subject_type", 1), ("path", 1), ("value_boolean", 1)], name="idx_qaf_boolean_lookup"
    )

    # Current-state reverse-traverse materialization.  Each replacement is
    # keyed by the source logical DPP; the remaining indexes mirror the
    # target and source-scope lookup shapes used by ``GET /query/traverse``.
    await db.dpp_reference.create_index(
        [
            ("target_subject_type", 1),
            ("target_dpp_id", 1),
            ("target_revision_number", 1),
            ("reference_type", 1),
        ],
        name="idx_ref_target_revision",
    )
    await db.dpp_reference.create_index(
        [("target_subject_type", 1), ("target_dpp_id", 1), ("reference_type", 1)],
        name="idx_ref_target_logical",
    )
    await db.dpp_reference.create_index(
        [("source_subject_type", 1), ("reference_path", 1)],
        name="idx_ref_source_path",
    )
    await db.dpp_reference.create_index(
        "source_logical_dpp_id", name="idx_ref_source_logical_dpp"
    )

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
