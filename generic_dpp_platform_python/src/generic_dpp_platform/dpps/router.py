import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from . import service as dpp_service
from .exceptions import NotFoundException
from .models import (
    DppDetailDTO,
    DppRevisionRequestDTO,
    DppRevisionResponseDTO,
    DppSummaryDTO,
)
from ..database import get_database

logger = structlog.get_logger()
router = APIRouter()


@router.get("", response_model=list[DppSummaryDTO])
async def list_all_dpps(
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[DppSummaryDTO]:
    logger.info("list_all_dpps")
    return await dpp_service.list_all_dpps(db)


@router.post("", response_model=DppRevisionResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_new_dpp(
        request: DppRevisionRequestDTO,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    logger.info("create_new_dpp", dpp_id=request.dpp_id)
    return await dpp_service.create_new_dpp(db, request)


@router.get("/{dpp_id}", response_model=DppDetailDTO)
async def get_dpp_detail(
        dpp_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppDetailDTO:
    logger.info("get_dpp_detail", dpp_id=dpp_id)
    try:
        return await dpp_service.get_dpp_detail(db, dpp_id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


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
