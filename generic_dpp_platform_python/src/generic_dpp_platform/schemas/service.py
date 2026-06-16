import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from .models import DppSchemaDTO

logger = structlog.get_logger()

_PROJECTION = {"_id": 0}


async def get_current_schema(
    db: AsyncIOMotorDatabase, subject_type: str
) -> DppSchemaDTO | None:
    if not await db.subject_types.find_one({"name": subject_type}):
        raise ValueError(f"Subject type not found: {subject_type}")

    doc = await db.schemas.find_one(
        {"subject_type": subject_type},
        _PROJECTION,
        sort=[("major_version", -1), ("minor_version", -1)],
    )
    return DppSchemaDTO(**doc) if doc else None


async def get_exact_schema(
    db: AsyncIOMotorDatabase,
    subject_type: str,
    major: int,
    minor: int,
) -> DppSchemaDTO | None:
    if not await db.subject_types.find_one({"name": subject_type}):
        raise ValueError(f"Subject type not found: {subject_type}")

    doc = await db.schemas.find_one(
        {"subject_type": subject_type, "major_version": major, "minor_version": minor},
        _PROJECTION,
    )
    return DppSchemaDTO(**doc) if doc else None


async def require_cached_schema_document(
    db: AsyncIOMotorDatabase,
    subject_type: str,
    major: int,
    minor: int,
) -> dict:
    """Return the exact cached schema document required by an imported revision.

    Administrative revision import is used after issuer migration to make a successor
    platform serve revisions that were already issued elsewhere. It must therefore
    reuse the platform's normal schema cache; it does not publish schemas or silently
    fetch missing schema versions. Scenario setup should call the existing
    ``cacheSchema`` endpoint first, then import revisions against that cached schema.
    """
    doc = await db.schemas.find_one(
        {"subject_type": subject_type, "major_version": major, "minor_version": minor},
        _PROJECTION,
    )
    if doc is None:
        raise ValueError(f"Schema not cached: {subject_type}/{major}.{minor}")
    return doc["schema_document"]


async def save_schemas(db: AsyncIOMotorDatabase, schemas: list[DppSchemaDTO]) -> int:
    saved = 0
    for schema in schemas:
        existing = await db.schemas.find_one(
            {
                "subject_type": schema.subject_type,
                "major_version": schema.major_version,
                "minor_version": schema.minor_version,
            }
        )
        if existing is None:
            await db.schemas.insert_one(schema.model_dump())
            saved += 1
    logger.info("schemas_saved", count=saved, subject_type=schemas[0].subject_type if schemas else None)
    return saved
