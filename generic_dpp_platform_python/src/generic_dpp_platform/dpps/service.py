import uuid
from datetime import UTC, datetime

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..admin import service as admin_service
from ..schemas.resolver_connector import resolve_dpp_revision
from . import cache_service
from . import cycle_detection as cycle_svc
from .exceptions import (
    DppAlreadyExistsException,
    DppReferenceResolutionException,
    DppRevisionConflictException,
    NotFoundException,
)
from .models import (
    DependencyType,
    DppRevisionRequestDTO,
    DppRevisionResponseDTO,
    DppRevisionSchemaDTO,
)
from .reference_extractor import extract_references
from .utils import hash_document, hash_to_hex, validate_dpp_document

logger = structlog.get_logger()


async def get_current_dpp_revision(
        db: AsyncIOMotorDatabase, dpp_id: str
) -> DppRevisionResponseDTO:
    return await get_dpp_revision(db, dpp_id, version=None)


async def get_dpp_revision(
        db: AsyncIOMotorDatabase, dpp_id: str, version: int | None
) -> DppRevisionResponseDTO:
    if not dpp_id:
        raise ValueError("dppId must not be empty")

    if not await db.logical_dpps.find_one({"dpp_id": dpp_id}):
        raise NotFoundException(f"DPP not found: {dpp_id}")

    if version is None:
        doc = await db.dpp_revisions.find_one(
            {"dpp_id": dpp_id}, {"_id": 0}, sort=[("dpp_version", -1)]
        )
    else:
        doc = await db.dpp_revisions.find_one(
            {"dpp_id": dpp_id, "dpp_version": version}, {"_id": 0}
        )

    if doc is None:
        raise NotFoundException(f"Revision not found: {dpp_id}/{version}")

    return _doc_to_response(doc)


async def create_new_dpp(
        db: AsyncIOMotorDatabase, request: DppRevisionRequestDTO
) -> DppRevisionResponseDTO:
    issuer_id = await _get_issuer_id(db)

    if not await db.subject_types.find_one({"name": request.schema_version.subject_type}):
        raise ValueError(f"Subject type not found: {request.schema_version.subject_type}")

    dpp_id = request.dpp_id
    if dpp_id is None:
        dpp_id = f"{issuer_id}-{uuid.uuid4()}"
    else:
        dpp_id = dpp_id.strip()
        if not dpp_id.startswith(issuer_id):
            raise ValueError(f"DPP ID must start with issuer ID: {issuer_id}")

    if await db.logical_dpps.find_one({"dpp_id": dpp_id}):
        raise DppAlreadyExistsException(f"DPP already exists: {dpp_id}")

    await db.logical_dpps.insert_one(
        {
            "dpp_id": dpp_id,
            "subject_type": request.schema_version.subject_type,
            "current_version": 0,
            "created_at": datetime.now(UTC),
        }
    )

    return await _create_revision(db, dpp_id, request, issuer_id)


async def create_dpp_revision_for_existing(
        db: AsyncIOMotorDatabase, dpp_id: str, request: DppRevisionRequestDTO
) -> DppRevisionResponseDTO:
    issuer_id = await _get_issuer_id(db)

    if not await db.logical_dpps.find_one({"dpp_id": dpp_id}):
        raise NotFoundException(f"DPP not found: {dpp_id}")

    return await _create_revision(db, dpp_id, request, issuer_id)


async def _create_revision(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        request: DppRevisionRequestDTO,
        issuer_id: str,
) -> DppRevisionResponseDTO:
    # Atomically acquire the next version number (Invariant I2)
    new_version = await _acquire_next_version(db, dpp_id, request.version)

    # Validate and fetch schema (Invariant I3)
    logical_dpp = await db.logical_dpps.find_one({"dpp_id": dpp_id})
    subject_type = logical_dpp["subject_type"]
    schema_doc = await _check_and_get_schema(db, request.schema_version, subject_type)

    # Validate payload against schema (Invariant I5)
    validated_payload = validate_dpp_document(request.dpp_payload, schema_doc)

    # Resolve and cache all hard references (Invariant I7)
    refs = extract_references(validated_payload)
    for ref in refs:
        if ref.dependency_type == DependencyType.HARD:
            await _resolve_and_cache_hard_reference(db, ref, issuer_id)

    # Cycle detection (Invariant I6)
    await cycle_svc.detect_cycles(
        db, subject_type, dpp_id, new_version, validated_payload, issuer_id
    )

    # Compute hash server-side (Invariant I4)
    payload_hash = hash_to_hex(hash_document(validated_payload))

    now = datetime.now(UTC)
    revision_doc = {
        "dpp_id": dpp_id,
        "dpp_version": new_version,
        "schema": {
            "subject_type": request.schema_version.subject_type,
            "major_version": request.schema_version.major_version,
            "minor_version": request.schema_version.minor_version,
        },
        "dpp_document": validated_payload,
        "hashed_document": payload_hash,
        "created_at": now,
    }
    await db.dpp_revisions.insert_one(revision_doc)
    logger.info("dpp_revision_created", dpp_id=dpp_id, version=new_version)

    return _doc_to_response(revision_doc)


async def _acquire_next_version(
        db: AsyncIOMotorDatabase, dpp_id: str, requested_version: int | None
) -> int:
    if requested_version is None:
        result = await db.logical_dpps.find_one_and_update(
            {"dpp_id": dpp_id},
            {"$inc": {"current_version": 1}},
            return_document=True,
        )
        return result["current_version"]

    # Explicit version: only accept if it equals current + 1
    result = await db.logical_dpps.find_one_and_update(
        {"dpp_id": dpp_id, "current_version": requested_version - 1},
        {"$inc": {"current_version": 1}},
        return_document=True,
    )
    if result is None:
        current = await db.logical_dpps.find_one({"dpp_id": dpp_id})
        expected = (current["current_version"] + 1) if current else 1
        raise DppRevisionConflictException(
            f"Version conflict: expected {expected}, got {requested_version}"
        )
    return result["current_version"]


async def _check_and_get_schema(
        db: AsyncIOMotorDatabase,
        schema_version: DppRevisionSchemaDTO,
        dpp_subject_type: str,
) -> dict:
    if schema_version.subject_type != dpp_subject_type:
        raise ValueError(
            f"Schema subject type '{schema_version.subject_type}' does not match "
            f"DPP subject type '{dpp_subject_type}'"
        )
    doc = await db.schemas.find_one(
        {
            "subject_type": schema_version.subject_type,
            "major_version": schema_version.major_version,
            "minor_version": schema_version.minor_version,
        }
    )
    if doc is None:
        raise ValueError(
            f"Schema version not found: {schema_version.subject_type} "
            f"{schema_version.major_version}.{schema_version.minor_version}"
        )
    return doc["schema_document"]


async def _resolve_and_cache_hard_reference(
        db: AsyncIOMotorDatabase, ref, issuer_id: str
) -> None:
    if ref.dpp_id.startswith(issuer_id):
        exists = await db.dpp_revisions.find_one(
            {"dpp_id": ref.dpp_id, "dpp_version": ref.version}
        )
        if not exists:
            raise DppReferenceResolutionException(
                f"{ref.subject_type}/{ref.dpp_id}/{ref.version}"
            )
        return

    cached = await cache_service.get_cached_revision(db, ref.dpp_id, ref.version)
    if cached:
        return

    response = await resolve_dpp_revision(db, ref.subject_type, ref.dpp_id, ref.version)
    revision_to_cache = {
        "dpp_id": response.dpp_id,
        "dpp_version": response.version,
        "subject_type": ref.subject_type,
        "schema_subject_type": response.schema_version.subject_type,
        "schema_major_version": response.schema_version.major_version,
        "schema_minor_version": response.schema_version.minor_version,
        "dpp_document": response.dpp_payload,
        "hashed_document": response.payload_hash,
        "created_at": response.created_at,
    }
    await cache_service.cache_revision(db, revision_to_cache)


async def _get_issuer_id(db: AsyncIOMotorDatabase) -> str:
    config = await admin_service.get_platform_config(db)
    issuer_id = config.issuer_id
    if not issuer_id:
        raise ValueError("Issuer ID is not configured")
    return issuer_id


def _doc_to_response(doc: dict) -> DppRevisionResponseDTO:
    schema = doc["schema"]
    return DppRevisionResponseDTO(
        dpp_id=doc["dpp_id"],
        version=doc["dpp_version"],
        schema_version=DppRevisionSchemaDTO(
            subject_type=schema["subject_type"],
            major_version=schema["major_version"],
            minor_version=schema["minor_version"],
        ),
        dpp_payload=doc["dpp_document"],
        payload_hash=doc["hashed_document"],
        created_at=doc["created_at"],
    )
