from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..database import get_database
from . import service
from .models import PlatformConfigDTO, SubjectTypeDTO

router = APIRouter()


@router.get("/platform-config", response_model=PlatformConfigDTO)
async def get_platform_config(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PlatformConfigDTO:
    return await service.get_platform_config(db)


@router.put("/platform-config", response_model=PlatformConfigDTO)
async def save_platform_config(
    config: PlatformConfigDTO,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PlatformConfigDTO:
    return await service.save_platform_config(db, config)


@router.get("/subject-types", response_model=list[SubjectTypeDTO])
async def get_subject_types(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[SubjectTypeDTO]:
    return await service.get_all_subject_types(db)


@router.post(
    "/subject-types",
    response_model=SubjectTypeDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_subject_type(
    dto: SubjectTypeDTO,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> SubjectTypeDTO:
    try:
        return await service.create_subject_type(db, dto)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/cache")
async def get_cache(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[dict]:
    return await db.referenced_dpp_revisions.find({}, {"_id": 0}).to_list(100)


@router.post("/reset")
async def reset_platform_data(
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Reset platform data (for scenario support)."""
    await db.referenced_dpp_revisions.delete_many({})
    await db.dpp_revisions.delete_many({})
    return {"status": "reset_complete"}
