"""
REST router exposing platform-local DPP operations.

The read endpoints expose locally hosted DPPs and revisions. They are also used by other platforms
after resolver indirection: the resolver maps an issuer-qualified DPP reference to the current
hosting platform, and the requesting platform then fetches the revision from this router.

The write endpoints implement the platform-side transition operations:
- POST /dpps/issue  implements the ``issue`` operation
- POST /dpps/{dpp_id}/revise  implements the ``revise`` operation

Paper references: Definitions 1, 2, 11; Invariants I1, I2, I3, I4, I5, I7.
"""
import structlog
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from . import service as dpp_service
from .models import (
    DppDetailDTO,
    DppRevisionClosureResponseDTO,
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
    """Return a summary list of all logical DPPs hosted on this platform."""
    logger.info("list_all_dpps")
    return await dpp_service.list_all_dpps(db)


@router.get("/{dpp_id}", response_model=DppDetailDTO)
async def get_dpp_detail(
        dpp_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppDetailDTO:
    """Return a logical DPP and all its locally stored revisions ordered by ascending version.

    Implements the derived current-revision notion and returns the full
    ordered revision history for audit purposes.
    """
    logger.info("get_dpp_detail", dpp_id=dpp_id)
    return await dpp_service.get_dpp_detail(db, dpp_id)


@router.get("/{dpp_id}/{revision_version}", response_model=DppRevisionResponseDTO)
async def get_specific_revision(
        dpp_id: str,
        revision_version: int,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    """Return a specific immutable revision using the direct response contract.

    This endpoint is the concrete platform target that another platform fetches after
    resolving a hard reference through the resolver (Definition 11: Resolution). 

    Args:
        dpp_id: the issuer-qualified DPP identifier
        revision_version: the concrete revision version
    """
    logger.info("get_specific_revision", dpp_id=dpp_id, version=revision_version)
    return await dpp_service.get_dpp_revision(db, dpp_id, revision_version)


@router.get("/{dpp_id}/{revision_version}/closure", response_model=DppRevisionClosureResponseDTO)
async def get_revision_closure(
        dpp_id: str,
        revision_version: int,
        max_depth: int = Query(..., ge=1, le=10),
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionClosureResponseDTO:
    """Return a bounded recursive hard-reference closure rooted at one revision.

    The response contains the root revision and unique hard-reference revisions reached
    up to ``max_depth``. ``max_depth=1`` resolves only direct hard references of the root;
    ``max_depth=2`` also resolves hard references of those direct dependencies. Soft
    references are not traversed. This endpoint is intended for validation, audit,
    offline caching, and benchmark scenarios.

    Args:
        dpp_id: the issuer-qualified DPP identifier
        revision_version: the concrete root revision version
        max_depth: positive traversal depth, bounded to the same limit as the Java platform
    """
    logger.info(
        "get_revision_closure",
        dpp_id=dpp_id,
        version=revision_version,
        max_depth=max_depth,
    )
    return await dpp_service.get_dpp_revision_closure(db, dpp_id, revision_version, max_depth)


@router.post("/issue", response_model=DppRevisionResponseDTO, status_code=status.HTTP_201_CREATED)
async def issue_dpp(
        request: DppRevisionRequestDTO,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    """Issue a new logical DPP and create its first immutable revision.

    This endpoint implements the platform-side ``issue`` operation from the transition system.

     It enforces:
    - I1: revision uniqueness via composite (dpp_id, version) key
    - I2: version monotonicity by assigning version 1 to the first revision
    - I3: schema explicitness by requiring the schema to be present in the local cache
    - I4: payload integrity by computing the hash server-side
    - I5: schema conformance by validating the payload against the pinned schema
    - I7: hard resolvability by resolving all hard references before committing

    Args:
        request: request containing the payload, schema version, optional DPP ID, and optional version
    """
    logger.info("issue_dpp", dpp_id=request.dpp_id)
    return await dpp_service.create_new_dpp(db, request)


@router.post("/{dpp_id}/revise", response_model=DppRevisionResponseDTO, status_code=status.HTTP_201_CREATED)
async def revise_existing_dpp(
        dpp_id: str,
        request: DppRevisionRequestDTO,
        db: AsyncIOMotorDatabase = Depends(get_database),
) -> DppRevisionResponseDTO:
    """Append a new immutable revision to an existing logical DPP.

    This endpoint implements the platform-side ``revise`` operation from the transition system. It enforces:

    - I1: revision uniqueness via composite (dpp_id, version) key
    - I2: version monotonicity by requiring next version = current max + 1
    - I3: schema explicitness by requiring the schema to be present in the local cache
    - I4: payload integrity by computing the hash server-side
    - I5: schema conformance by validating the payload against the pinned schema
    - I7: hard resolvability by resolving all hard references before committing

    Version acquisition is atomic via MongoDB findOneAndUpdate with $inc, preventing
    concurrent revise requests from assigning the same version number.

    Args:
        dpp_id: the issuer-qualified DPP identifier
        request: request containing the payload, schema version, and optional next version
    """
    logger.info("revise_existing_dpp", dpp_id=dpp_id)
    return await dpp_service.create_dpp_revision_for_existing(db, dpp_id, request)
