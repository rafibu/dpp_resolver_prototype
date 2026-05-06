import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from . import service as dpp_service
from .exceptions import (
    NotFoundException,
)
from .models import DppRevisionRequestDTO, DppRevisionResponseDTO
from ..database import get_database

logger = structlog.get_logger()
router = APIRouter()


@router.post("", response_model=DppRevisionResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_new_dpp(
        request: DppRevisionRequestDTO,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    logger.info("create_new_dpp", dpp_id=request.dpp_id)
    return await dpp_service.create_new_dpp(db, request)


@router.get("/{dpp_id}", response_model=DppRevisionResponseDTO)
async def get_current_revision(
        dpp_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    logger.info("get_current_revision", dpp_id=dpp_id)
    return await dpp_service.get_current_dpp_revision(db, dpp_id)


@router.post("/{dpp_id}", response_model=DppRevisionResponseDTO, status_code=status.HTTP_201_CREATED)
async def append_revision(
        dpp_id: str,
        request: DppRevisionRequestDTO,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    logger.info("append_revision", dpp_id=dpp_id)
    return await dpp_service.create_dpp_revision_for_existing(db, dpp_id, request)


@router.get("/{dpp_id}/{revision_version}", response_model=DppRevisionResponseDTO)
async def get_specific_revision(
        dpp_id: str,
        revision_version: int,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    logger.info("get_specific_revision", dpp_id=dpp_id, version=revision_version)
    return await dpp_service.get_dpp_revision(db, dpp_id, revision_version)
