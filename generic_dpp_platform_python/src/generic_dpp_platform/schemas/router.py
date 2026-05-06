import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..database import get_database
from . import resolver_connector
from . import service as schema_service
from .models import DppSchemaDTO

logger = structlog.get_logger()
router = APIRouter()


@router.get("/{subject_type}", response_model=DppSchemaDTO | None)
async def get_current_schema(
    subject_type: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppSchemaDTO | None:
    logger.info("retrieving_current_schema", subject_type=subject_type)
    try:
        return await schema_service.get_current_schema(db, subject_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{subject_type}/{major}/{minor}", response_model=DppSchemaDTO | None)
async def get_exact_schema(
    subject_type: str,
    major: int,
    minor: int,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppSchemaDTO | None:
    logger.info("retrieving_exact_schema", subject_type=subject_type, major=major, minor=minor)
    try:
        return await schema_service.get_exact_schema(db, subject_type, major, minor)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{subject_type}/sync", status_code=status.HTTP_200_OK)
async def sync_schema(
    subject_type: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> None:
    logger.info("syncing_schema", subject_type=subject_type)
    try:
        await resolver_connector.sync_schema(db, subject_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
