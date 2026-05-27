"""
REST router for platform administration endpoints.

Exposes helper endpoints for platform configuration, subject type registration, and the
external-revision cache used to support hard-reference resolution (Invariant I7).

The cache and reset endpoints are utility operations used in scenarios to observe and reset
platform state without modifying issued DPP revisions or the resolver registry.
"""
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
    """Return the current platform configuration."""
    return await service.get_platform_config(db)


@router.put("/platform-config", response_model=PlatformConfigDTO)
async def save_platform_config(
    config: PlatformConfigDTO,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PlatformConfigDTO:
    """Update the platform configuration. Only non-null fields are applied."""
    return await service.save_platform_config(db, config)


@router.get("/subject-types", response_model=list[SubjectTypeDTO])
async def get_subject_types(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[SubjectTypeDTO]:
    """Return all subject types registered on this platform.

    Subject types correspond to Definition 3 (Schema artefact) in the paper: each subject type
    governs a product domain and is validated by its own schema family.
    """
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
    """Register a new subject type on this platform.

    This is a helper endpoint for administrative registration. It could also be performed
    directly at database initialization or through direct DB input.
    """
    try:
        return await service.create_subject_type(db, dto)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/cache")
async def get_cache(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[dict]:
    """Return all externally cached DPP revisions.

    These are hard-reference targets fetched from other platforms and stored locally to
    support Invariant I7 (hard resolvability) without repeated resolver round-trips.
    """
    return await db.referenced_dpp_revisions.find({}, {"_id": 0}).to_list(100)


@router.post("/reset")
async def reset_platform_data(
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Clear the external-revision cache for a clean scenario start.

    Removes all cached external DPP revisions from the referenced_dpp_revisions collection.
    Used in scenarios (S1, S2) to reset the platform to a known state before exercising
    offline interpretability or schema evolution behavior.
    """
    await db.referenced_dpp_revisions.delete_many({})
    await db.dpp_revisions.delete_many({})
    await db.logical_dpps.delete_many({})
    return {"status": "reset_complete"}
