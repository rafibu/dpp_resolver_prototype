import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from .models import PlatformConfigDTO, SubjectTypeDTO
from ..dpps.models import DppRevisionResponseDTO
from ..schemas import service as schema_service

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


async def require_subject_type(db: AsyncIOMotorDatabase, name: str) -> SubjectTypeDTO:
    """Return a registered subject type for service-level orchestration.

    Admin workflows such as revision import are not allowed to create implicit subject
    types. They must reuse the same subject-type registration path as issue/revise, so
    this helper centralizes the prerequisite check instead of letting routers reach into
    collections directly.
    """
    doc = await db.subject_types.find_one({"name": name}, _SUBJECT_PROJECTION)
    if doc is None:
        raise ValueError(f"Subject type not found: {name}")
    return SubjectTypeDTO(**doc)


async def import_revisions(
    db: AsyncIOMotorDatabase,
    revisions: list[DppRevisionResponseDTO],
) -> list[DppRevisionResponseDTO]:
    """Import already-issued immutable revisions into this platform.

    Scenario S1 uses this operation during issuer migration: revisions are copied to a
    successor platform and the resolver route is then moved to that successor. This
    function coordinates existing platform services instead of becoming a separate DPP
    lifecycle path:

    - subject type registration is checked through the admin subject-type service;
    - exact schema availability is checked through the schema service's cache lookup;
    - revision persistence and hash validation are delegated to the DPP service.

    Revisions are processed in DPP/version order to make multi-version imports
    deterministic, and the DPP service makes retries idempotent.
    """
    from ..dpps import service as dpp_service

    imported: list[DppRevisionResponseDTO] = []
    for revision in sorted(revisions, key=lambda item: (item.dpp_id, item.version)):
        schema_version = revision.schema_version
        await require_subject_type(db, schema_version.subject_type)
        schema_document = await schema_service.require_cached_schema_document(
            db,
            schema_version.subject_type,
            schema_version.major_version,
            schema_version.minor_version,
        )
        imported.append(await dpp_service.import_existing_revision(db, revision, schema_document))

    return imported
