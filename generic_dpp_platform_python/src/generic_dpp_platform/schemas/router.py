"""
REST router for platform-local schema cache access.

This router does not publish schemas and does not mutate the resolver's authoritative schema set.
It exposes schemas that this DPP platform has already cached from the resolver and provides a
manual trigger for the platform-side ``cacheSchema`` operation.

Resolver-side operations such as schema publication, compatibility checking, and schema-dependency
graph acyclicity are intentionally outside this router.

Paper references: Definition 3 (Schema artefact), Invariant I3 (Schema explicitness),
``cacheSchema`` operation.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..database import get_database
from . import resolver_connector
from . import service as schema_service
from .models import DppSchemaDTO

logger = structlog.get_logger()
router = APIRouter()


@router.get("/{subject_type}", response_model=DppSchemaDTO)
async def get_current_schema(
        subject_type: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppSchemaDTO:
    """Return the newest locally cached schema for a subject type.

    Returns the schema with the highest (major, minor) version pair. Returns 404 if the
    subject type is not registered on this platform or has no cached schema yet.
    """
    logger.info("retrieving_current_schema", subject_type=subject_type)
    try:
        schema = await schema_service.get_current_schema(db, subject_type)
        if schema is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No schema found for {subject_type}",
            )
        return schema
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{subject_type}/{major}/{minor}", response_model=DppSchemaDTO)
async def get_exact_schema(
        subject_type: str,
        major: int,
        minor: int,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppSchemaDTO:
    """Return an exact locally cached schema version.

    Returns 404 if the subject type is not registered on this platform or the requested
    version is not in the local cache.
    """
    logger.info("retrieving_exact_schema", subject_type=subject_type, major=major, minor=minor)
    try:
        schema = await schema_service.get_exact_schema(db, subject_type, major, minor)
        if schema is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No schema found for {subject_type} with version {major}.{minor}",
            )
        return schema
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{subject_type}/cacheSchema", status_code=status.HTTP_200_OK)
async def cache_schema_manually(
        subject_type: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> None:
    """Manually fetch schemas for a subject type from the resolver into the local platform cache.

    This endpoint implements the platform-side ``cacheSchema`` operation (Section 5.1.3). It
    does not create schemas; it only copies resolver-published schemas into this platform's cache
    so that payloads can be validated during issue and revise.

    Args:
        subject_type: the subject type whose schemas should be cached from the resolver
    """
    logger.info("caching_schema", subject_type=subject_type)
    try:
        await resolver_connector.cache_schema(db, subject_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
