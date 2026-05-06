import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from .models import PlatformConfigDTO, SubjectTypeDTO

logger = structlog.get_logger()

_CONFIG_PROJECTION = {"_id": 0}
_SUBJECT_PROJECTION = {"_id": 0}


async def get_platform_config(db: AsyncIOMotorDatabase) -> PlatformConfigDTO:
    doc = await db.platform_config.find_one({}, _CONFIG_PROJECTION)
    if doc is None:
        return PlatformConfigDTO()
    return PlatformConfigDTO(**doc)


async def save_platform_config(
    db: AsyncIOMotorDatabase, config: PlatformConfigDTO
) -> PlatformConfigDTO:
    update_fields = {k: v for k, v in config.model_dump().items() if v is not None}
    await db.platform_config.update_one({}, {"$set": update_fields}, upsert=True)
    logger.info("platform_config_updated", fields=list(update_fields.keys()))
    return await get_platform_config(db)


async def get_all_subject_types(db: AsyncIOMotorDatabase) -> list[SubjectTypeDTO]:
    cursor = db.subject_types.find({}, _SUBJECT_PROJECTION)
    docs = await cursor.to_list(length=None)
    return [SubjectTypeDTO(**doc) for doc in docs]


async def create_subject_type(
    db: AsyncIOMotorDatabase, dto: SubjectTypeDTO
) -> SubjectTypeDTO:
    existing = await db.subject_types.find_one({"name": dto.name})
    if existing is not None:
        raise ValueError(f"Subject type already exists: {dto.name}")
    doc = dto.model_dump()
    await db.subject_types.insert_one(doc)
    logger.info("subject_type_created", name=dto.name)
    return SubjectTypeDTO(**{k: v for k, v in doc.items() if k != "_id"})
