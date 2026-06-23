import asyncio
import structlog
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from motor.motor_asyncio import AsyncIOMotorClientSession, AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import OperationFailure

from . import cache_service
from .exceptions import (
    DppAlreadyExistsException,
    DppReferenceResolutionException,
    DppRevisionConflictException,
    NotFoundException,
)
from .models import (
    DependencyType,
    DppDetailDTO,
    DppRevisionClosureResponseDTO,
    DppRevisionRequestDTO,
    DppRevisionResponseDTO,
    DppRevisionSchemaDTO,
    DppRevisionSummary,
    DppSummaryDTO,
)
from .reference_extractor import extract_references
from .utils import hash_document, hash_to_hex, validate_dpp_document
from ..admin import service as admin_service
from ..queries.index import replace_materialized_facts, replace_materialized_references
from ..schemas.resolver_connector import cache_schema, resolve_dpp_revision

logger = structlog.get_logger()

DPP_ID_ISSUER_SEPARATOR = "-"
_TRANSACTION_RETRY_LIMIT = 5
_DIRECT_REVISION_RESOLUTION_DEPTH = 1
_MAX_CLOSURE_DEPTH = 10


@dataclass(frozen=True)
class _RevisionResolutionResult:
    root_revision: DppRevisionResponseDTO
    resolved_revisions: list[DppRevisionResponseDTO]


async def list_all_dpps(db: AsyncIOMotorDatabase) -> list[DppSummaryDTO]:
    summaries = []
    async for dpp in db.logical_dpps.find({}, {"_id": 0}):
        latest = await db.dpp_revisions.find_one(
            {"dpp_id": dpp["dpp_id"]},
            {"_id": 0},
            sort=[("dpp_version", -1)],
        )
        summaries.append(
            DppSummaryDTO(
                dpp_id=dpp["dpp_id"],
                subject_type=dpp["subject_type"],
                current_version=dpp.get("current_version", 0),
                last_updated=str(latest["created_at"]) if latest else str(dpp.get("created_at", "")),
            )
        )
    return summaries


async def get_dpp_detail(db: AsyncIOMotorDatabase, dpp_id: str) -> DppDetailDTO:
    dpp_doc = await db.logical_dpps.find_one({"dpp_id": dpp_id}, {"_id": 0})
    if not dpp_doc:
        raise NotFoundException(f"DPP not found: {dpp_id}")

    revision_docs = await db.dpp_revisions.find(
        {"dpp_id": dpp_id},
        {"_id": 0},
        sort=[("dpp_version", 1)],
    ).to_list(None)

    revisions = [
        DppRevisionSummary(
            version=r["dpp_version"],
            schema_ref="{}/{}.{}".format(
                r["schema"]["subject_type"],
                r["schema"]["major_version"],
                r["schema"]["minor_version"],
            ),
            hash=r["hashed_document"],
            payload=r["dpp_document"],
        )
        for r in revision_docs
    ]

    return DppDetailDTO(
        dpp_id=dpp_id,
        subject_type=dpp_doc["subject_type"],
        revisions=revisions,
    )


async def get_current_dpp_revision(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
) -> DppRevisionResponseDTO:
    return await get_dpp_revision(db, dpp_id, version=None)


async def get_dpp_revision(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        version: int | None,
) -> DppRevisionResponseDTO:
    """Return the requested revision while preserving the direct response contract.

    Direct revision retrieval routes through the shared resolution helper with a depth of
    one, but it returns only the root revision. It does not expose the bounded recursive
    hard-reference closure; callers that need that should use ``get_dpp_revision_closure``.
    """
    result = await _resolve_dpp_revision(
        db=db,
        dpp_id=dpp_id,
        version=version,
        max_depth=_DIRECT_REVISION_RESOLUTION_DEPTH,
        expand_closure=False,
    )
    return result.root_revision


async def get_dpp_revision_closure(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        version: int,
        max_depth: int,
) -> DppRevisionClosureResponseDTO:
    """Return a bounded recursive hard-reference closure rooted at one revision.

    Closure resolution returns the root revision and each unique hard-reference revision
    reached by recursively traversing payload references up to ``max_depth``. A depth of
    one resolves only direct hard references of the root revision; a depth of two also
    resolves hard references of those directly referenced revisions. Soft references are
    never traversed. The traversal is bounded for validation, audit, offline caching, and
    benchmark scenarios.
    """
    _validate_max_depth(max_depth)
    result = await _resolve_dpp_revision(
        db=db,
        dpp_id=dpp_id,
        version=version,
        max_depth=max_depth,
        expand_closure=True,
    )
    return DppRevisionClosureResponseDTO(
        root_revision=result.root_revision,
        resolved_revisions=result.resolved_revisions,
    )


async def _resolve_dpp_revision(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        version: int | None,
        max_depth: int,
        expand_closure: bool,
) -> _RevisionResolutionResult:
    root_revision = await _load_dpp_revision(db, dpp_id, version)

    if not expand_closure:
        return _RevisionResolutionResult(root_revision=root_revision, resolved_revisions=[])

    issuer_id = await _get_issuer_id(db)
    resolved_revisions: dict[tuple[str, int], DppRevisionResponseDTO] = {}
    visited: set[tuple[str, int]] = {(root_revision.dpp_id, root_revision.version)}
    queue = deque([(root_revision, 0)])

    while queue:
        revision, depth = queue.popleft()
        if depth >= max_depth:
            continue

        for ref in _extract_sorted_hard_references(revision):
            key = (ref.dpp_id, ref.version)
            if key in visited:
                continue

            visited.add(key)
            resolved = await _resolve_and_cache_hard_reference(db, ref, issuer_id)
            resolved_revisions[key] = resolved
            queue.append((resolved, depth + 1))

    return _RevisionResolutionResult(
        root_revision=root_revision,
        resolved_revisions=list(resolved_revisions.values()),
    )


async def _load_dpp_revision(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        version: int | None,
) -> DppRevisionResponseDTO:
    if not dpp_id:
        raise ValueError("DPP id must not be empty")

    if not await db.logical_dpps.find_one({"dpp_id": dpp_id}):
        raise NotFoundException(f"DPP not found: {dpp_id}")

    if version is None:
        doc = await db.dpp_revisions.find_one(
            {"dpp_id": dpp_id},
            {"_id": 0},
            sort=[("dpp_version", -1)],
        )
    else:
        doc = await db.dpp_revisions.find_one(
            {"dpp_id": dpp_id, "dpp_version": version},
            {"_id": 0},
        )

    if doc is None:
        raise NotFoundException(f"Revision not found: {dpp_id}/{version}")

    return _doc_to_response(doc)


def _validate_max_depth(max_depth: int) -> None:
    if max_depth < 1 or max_depth > _MAX_CLOSURE_DEPTH:
        raise ValueError(f"max_depth must be between 1 and {_MAX_CLOSURE_DEPTH}")


def _extract_sorted_hard_references(revision: DppRevisionResponseDTO):
    return sorted(
        (
            ref
            for ref in extract_references(revision.dpp_payload)
            if ref.dependency_type == DependencyType.HARD
        ),
        key=lambda ref: (
            ref.subject_type or "",
            ref.dpp_id or "",
            ref.version or 0,
            ref.json_path or "",
        ),
    )


async def create_new_dpp(
        db: AsyncIOMotorDatabase,
        request: DppRevisionRequestDTO,
) -> DppRevisionResponseDTO:
    """
    Implement the platform-side ``issue`` operation.

        The issue operation creates a new Definition 1 logical DPP and its first Definition 2 revision.

        Where the invariants kick in:

        - I1: before insertion, the service rejects an already existing logical DPP ID; the revision
          itself is stored under the unique ``(dpp_id, dpp_version)`` key.
        - I2: the first revision must be version 1. If the client supplies a version, it must be 1.
        - I3: the request must name an exact schema version. If the schema is missing locally, the
          platform synchronizes schemas from the resolver and retries the lookup.
        - I4: the payload hash is computed server-side from the validated payload before storage.
        - I5: the payload is validated against the pinned schema before any revision is stored.
        - I7: all hard references extracted from the validated payload must resolve before commit.

        The logical DPP document and revision document are inserted in one MongoDB transaction. This
        prevents an empty logical DPP from remaining if revision insertion fails.
    """
    issuer_id = await _get_issuer_id(db)

    if not await db.subject_types.find_one({"name": request.schema_version.subject_type}):
        raise ValueError(f"Subject type not found: {request.schema_version.subject_type}")

    dpp_id = _normalize_or_generate_dpp_id(request.dpp_id, issuer_id)

    if await db.logical_dpps.find_one({"dpp_id": dpp_id}):
        raise DppAlreadyExistsException(f"DPP already exists: {dpp_id}")

    if request.version is not None and request.version != 1:
        raise DppRevisionConflictException(f"Version must be 1 if no revisions exist. Got: {request.version}")

    subject_type = request.schema_version.subject_type
    revision_doc = await _prepare_revision_doc(
        db=db,
        dpp_id=dpp_id,
        version=1,
        subject_type=subject_type,
        request=request,
        issuer_id=issuer_id,
    )

    now = revision_doc["created_at"]

    async with await db.client.start_session() as session:
        async with session.start_transaction():
            if await db.logical_dpps.find_one({"dpp_id": dpp_id}, session=session):
                raise DppAlreadyExistsException(f"DPP already exists: {dpp_id}")

            await db.logical_dpps.insert_one(
                {
                    "dpp_id": dpp_id,
                    "subject_type": subject_type,
                    "current_version": 1,
                    "created_at": now,
                },
                session=session,
            )

            await db.dpp_revisions.insert_one(revision_doc, session=session)
            await replace_materialized_facts(
                db,
                dpp_id,
                subject_type,
                revision_doc["dpp_document"],
                session=session,
            )
            await replace_materialized_references(
                db,
                dpp_id,
                subject_type,
                revision_doc["dpp_document"],
                session=session,
            )

    logger.info("dpp_revision_created", dpp_id=dpp_id, version=1)
    return _doc_to_response(revision_doc)


async def create_dpp_revision_for_existing(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        request: DppRevisionRequestDTO,
) -> DppRevisionResponseDTO:
    """
    Implement the platform-side ``revise`` operation.

    The revise operation appends one new Definition 2 revision to an existing Definition 1 logical DPP.

    Where the invariants kick in:

    - I1: the new revision is inserted under the unique ``(dpp_id, dpp_version)`` key.
    - I2: the next version is obtained by atomically incrementing ``current_version`` by exactly
      one. If the client supplies a version, the update only succeeds when it equals current + 1.
    - I3: the revision must name an exact schema version that is available after resolver
      synchronization.
    - I4: the payload hash is computed from the validated payload before storage.
    - I5: the payload is validated against the pinned schema before a version number is consumed.
    - I7: every hard reference must resolve before a version number is consumed.

    Version acquisition and revision insertion are transactionally coupled. If revision insertion
    fails, the version increment is rolled back, preserving I2 density.
    """
    issuer_id = await _get_issuer_id(db)

    logical_dpp = await db.logical_dpps.find_one({"dpp_id": dpp_id})
    if not logical_dpp:
        raise NotFoundException(f"DPP not found: {dpp_id}")

    subject_type = logical_dpp["subject_type"]

    # Validate schema, payload, and hard references before taking the version number.
    # This keeps the transaction short and prevents needless version increments for invalid requests.
    prepared_without_version = await _prepare_revision_components(
        db=db,
        subject_type=subject_type,
        request=request,
        issuer_id=issuer_id,
    )

    revision_doc: dict = {}
    async with await db.client.start_session() as session:
        for attempt in range(_TRANSACTION_RETRY_LIMIT):
            try:
                async with session.start_transaction():
                    if not await db.logical_dpps.find_one({"dpp_id": dpp_id}, session=session):
                        raise NotFoundException(f"DPP not found: {dpp_id}")

                    new_version = await _acquire_next_version(
                        db=db,
                        dpp_id=dpp_id,
                        requested_version=request.version,
                        session=session,
                    )

                    revision_doc = _build_revision_doc(
                        dpp_id=dpp_id,
                        version=new_version,
                        schema_version=request.schema_version,
                        validated_payload=prepared_without_version["validated_payload"],
                        payload_hash=prepared_without_version["payload_hash"],
                        created_at=prepared_without_version["created_at"],
                    )

                    await db.dpp_revisions.insert_one(revision_doc, session=session)
                    await replace_materialized_facts(
                        db,
                        dpp_id,
                        subject_type,
                        revision_doc["dpp_document"],
                        session=session,
                    )
                    await replace_materialized_references(
                        db,
                        dpp_id,
                        subject_type,
                        revision_doc["dpp_document"],
                        session=session,
                    )
                break  # Transaction committed successfully
            except OperationFailure as exc:
                labels = (exc.details or {}).get("errorLabels", [])
                if "TransientTransactionError" not in labels or attempt == _TRANSACTION_RETRY_LIMIT - 1:
                    raise
                # Concurrent revisions can repeatedly collide if every caller
                # retries its Mongo transaction immediately.  A tiny bounded
                # backoff lets the winning transaction commit before the next
                # optimistic attempt.
                await asyncio.sleep(0.01 * (attempt + 1))

    logger.info("dpp_revision_created", dpp_id=dpp_id, version=revision_doc["dpp_version"])
    return _doc_to_response(revision_doc)


async def import_existing_revision(
        db: AsyncIOMotorDatabase,
        revision: DppRevisionResponseDTO,
        schema_document: dict,
) -> DppRevisionResponseDTO:
    """Persist one copied immutable revision for an issuer-migration import.

    This function is the DPP-service part of the administrative import endpoint. It is
    intentionally not a replacement for ``create_new_dpp`` or
    ``create_dpp_revision_for_existing``: no new revision is authored here. Instead, a
    successor platform stores a revision that was already issued by the previous hosting
    platform so resolver migration can keep hard and soft references resolvable.

    The method reuses the same stored document shape and invariant checks that apply to
    normal revisions where they are relevant:

    - I5: validate the copied payload against the exact cached schema.
    - I4: recompute and compare the copied payload hash before storing.
    - Logical DPP grouping: create or reuse the logical DPP record for the imported ID.
    - Idempotency: return an existing imported revision unchanged when migration retries.

    Hard references are not resolved during import because the incoming revision is a
    historical artefact. Resolving dependencies here would turn migration into a fresh
    issue/revise transition instead of copying the already-issued revision.
    """
    _validate_imported_revision_envelope(revision)

    schema_version = revision.schema_version
    subject_type = schema_version.subject_type
    existing_logical = await db.logical_dpps.find_one({"dpp_id": revision.dpp_id})
    if existing_logical and existing_logical["subject_type"] != subject_type:
        raise ValueError("Imported revisions for one DPP must use one subject type")

    validated_payload = validate_dpp_document(revision.dpp_payload, schema_document)
    computed_hash = hash_to_hex(hash_document(validated_payload))
    if computed_hash != revision.payload_hash:
        raise ValueError(f"Imported revision payload hash mismatch for {revision.dpp_id}")

    revision_doc = _build_revision_doc(
        dpp_id=revision.dpp_id,
        version=revision.version,
        schema_version=schema_version,
        validated_payload=validated_payload,
        payload_hash=revision.payload_hash,
        created_at=revision.created_at,
    )

    async with await db.client.start_session() as session:
        async with session.start_transaction():
            existing_revision = await db.dpp_revisions.find_one(
                {"dpp_id": revision.dpp_id, "dpp_version": revision.version},
                {"_id": 0},
                session=session,
            )
            if existing_revision:
                return _doc_to_response(existing_revision)

            logical = await db.logical_dpps.find_one({"dpp_id": revision.dpp_id}, session=session)
            if logical and logical["subject_type"] != subject_type:
                raise ValueError("Imported revisions for one DPP must use one subject type")
            if logical is None:
                await db.logical_dpps.insert_one(
                    {
                        "dpp_id": revision.dpp_id,
                        "subject_type": subject_type,
                        "current_version": revision.version,
                        "created_at": revision.created_at,
                    },
                    session=session,
                )
            else:
                await db.logical_dpps.update_one(
                    {"dpp_id": revision.dpp_id, "current_version": {"$lt": revision.version}},
                    {"$set": {"current_version": revision.version}},
                    session=session,
                )

            await db.dpp_revisions.insert_one(revision_doc, session=session)

    # Imported revisions may be historical.  Rebuild facts only when this is
    # the current revision for the logical DPP, preserving the same current
    # view as normal issue/revise operations.
    current = await db.logical_dpps.find_one({"dpp_id": revision.dpp_id}, {"_id": 0})
    if current and current["current_version"] == revision.version:
        await replace_materialized_facts(
            db,
            revision.dpp_id,
            subject_type,
            revision_doc["dpp_document"],
        )
        await replace_materialized_references(
            db,
            revision.dpp_id,
            subject_type,
            revision_doc["dpp_document"],
        )

    logger.info("dpp_revision_imported", dpp_id=revision.dpp_id, version=revision.version)
    return _doc_to_response(revision_doc)


def _validate_imported_revision_envelope(revision: DppRevisionResponseDTO) -> None:
    if not revision.dpp_id:
        raise ValueError("dpp_id is required for imported revisions")
    if revision.version < 1:
        raise ValueError("version must be positive for imported revisions")
    if not revision.payload_hash:
        raise ValueError("payload_hash is required for imported revisions")


async def _prepare_revision_doc(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        version: int,
        subject_type: str,
        request: DppRevisionRequestDTO,
        issuer_id: str,
) -> dict:
    """
    Build a revision document after checking I3, I5, I7, and I4.

    This helper is used by issue, where the version is known to be 1 before persistence.
    """
    components = await _prepare_revision_components(
        db=db,
        subject_type=subject_type,
        request=request,
        issuer_id=issuer_id,
    )

    return _build_revision_doc(
        dpp_id=dpp_id,
        version=version,
        schema_version=request.schema_version,
        validated_payload=components["validated_payload"],
        payload_hash=components["payload_hash"],
        created_at=components["created_at"],
    )


async def _prepare_revision_components(
        db: AsyncIOMotorDatabase,
        subject_type: str,
        request: DppRevisionRequestDTO,
        issuer_id: str,
) -> dict:
    """Prepare the semantic content of a revision before it receives a version.

    This helper performs the non-version checks common to issue and revise:

    - I3: load the exact pinned schema, synchronizing from the resolver if needed.
    - I5: validate the payload against that schema.
    - Definition 12: extract references from the validated payload.
    - I7: resolve all hard references.
    - I4: compute the hash of the validated payload.

    Soft references are intentionally ignored after extraction because they are not part of I7.
    """
    schema_doc = await _check_and_get_schema(db, request.schema_version, subject_type)
    validated_payload = validate_dpp_document(request.dpp_payload, schema_doc)

    refs = extract_references(validated_payload)
    for ref in refs:
        if ref.dependency_type == DependencyType.HARD:
            await _resolve_and_cache_hard_reference(db, ref, issuer_id)

    payload_hash = hash_to_hex(hash_document(validated_payload))

    return {
        "validated_payload": validated_payload,
        "payload_hash": payload_hash,
        "created_at": datetime.now(UTC),
    }


async def _acquire_next_version(
        db: AsyncIOMotorDatabase,
        dpp_id: str,
        requested_version: int | None,
        session: AsyncIOMotorClientSession,
) -> int:
    """Acquire the next revision version while preserving I2.

    I2 requires a gap-free linear sequence. The MongoDB document for the logical DPP stores the
    current maximum version. This helper increments it by exactly one inside the same transaction
    that later inserts the revision.

    If the client provides an explicit version, the update predicate includes
    ``current_version == requested_version - 1``. Therefore the operation succeeds only for the
    next consecutive version.
    """
    if requested_version is None:
        result = await db.logical_dpps.find_one_and_update(
            {"dpp_id": dpp_id},
            {"$inc": {"current_version": 1}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if result is None:
            raise NotFoundException(f"DPP not found: {dpp_id}")
        return result["current_version"]

    result = await db.logical_dpps.find_one_and_update(
        {"dpp_id": dpp_id, "current_version": requested_version - 1},
        {"$inc": {"current_version": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )

    if result is None:
        current = await db.logical_dpps.find_one({"dpp_id": dpp_id}, session=session)
        expected = (current["current_version"] + 1) if current else 1
        raise DppRevisionConflictException(
            f"Version conflict. Expected: {expected}, Got: {requested_version}"
        )

    return result["current_version"]


async def _check_and_get_schema(
        db: AsyncIOMotorDatabase,
        schema_version: DppRevisionSchemaDTO,
        dpp_subject_type: str,
) -> dict:
    """Load the exact schema required by I3 and I5.

    I3 requires the revision to explicitly name a schema artefact. I5 requires the payload to
    validate against that schema. Operationally, this platform first checks its local schema cache.
    If the exact version is missing, it executes the platform-side cacheSchema operation by asking
    the resolver for schemas of the requested subject type, then retries the exact lookup.

    The subject type in the schema reference must match the logical DPP subject type. This preserves
    the interpretation that each DPP is governed by the schema family of its subject type.
    """
    if schema_version.subject_type != dpp_subject_type:
        raise ValueError(
            f"Schema subject type {schema_version.subject_type} does not match "
            f"the DPP subject type {dpp_subject_type}"
        )

    query = {
        "subject_type": schema_version.subject_type,
        "major_version": schema_version.major_version,
        "minor_version": schema_version.minor_version,
    }

    doc = await db.schemas.find_one(query)
    if doc is not None:
        return doc["schema_document"]

    logger.info(
        "schema_not_in_local_cache_syncing_from_resolver",
        subject_type=schema_version.subject_type,
        major=schema_version.major_version,
        minor=schema_version.minor_version,
    )

    try:
        await cache_schema(db, schema_version.subject_type)
    except Exception as exc:
        logger.warning(
            "resolver_sync_failed_falling_back_to_local_cache",
            subject_type=schema_version.subject_type,
            error=str(exc),
        )

    doc = await db.schemas.find_one(query)
    if doc is None:
        raise ValueError(
            "Schema version not found after resolver synchronization: "
            f"{schema_version.subject_type}/{schema_version.major_version}.{schema_version.minor_version}"
        )

    return doc["schema_document"]


async def _resolve_and_cache_hard_reference(
        db: AsyncIOMotorDatabase,
        ref,
        issuer_id: str,
) -> DppRevisionResponseDTO:
    """Resolve one hard reference as required by I7 and return the target revision.

    A hard reference names a concrete revision. The platform must verify that this target exists
    before committing the new revision. Closure traversal reuses this helper so unresolved
    references fail with the same platform conventions as issue/revise.

    Resolution strategy:

    1. If the target DPP ID belongs to this issuer, load it from the local revision collection.
    2. Otherwise, check the external revision cache.
    3. If absent from the cache, use resolver-based resolution (Definition 11) to fetch the target
       revision from its current hosting platform.
    4. Cache the fetched revision for later use.

    Soft references are never passed to this helper.
    """
    if _is_dpp_id_owned_by_issuer(ref.dpp_id, issuer_id):
        doc = await db.dpp_revisions.find_one(
            {"dpp_id": ref.dpp_id, "dpp_version": ref.version}, {"_id": 0}
        )
        if not doc:
            raise DppReferenceResolutionException(
                f"{ref.subject_type}/{ref.dpp_id}/{ref.version}"
            )
        return _doc_to_response(doc)

    cached = await cache_service.get_cached_revision(db, ref.dpp_id, ref.version)
    if cached:
        logger.info("using_cached_revision_for_hard_reference", ref=ref.original_ref)
        return _cached_doc_to_response(cached)

    logger.info("resolving_external_hard_reference", ref=ref.original_ref)

    response = await resolve_dpp_revision(db, ref.subject_type, ref.dpp_id, ref.version)
    if response is None:
        raise DppReferenceResolutionException(
            f"Resolver returned null for {ref.original_ref}"
        )

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
        "fetched_at": datetime.now(UTC),
    }
    await cache_service.cache_revision(db, revision_to_cache)
    return response


async def _get_issuer_id(db: AsyncIOMotorDatabase) -> str:
    config = await admin_service.get_platform_config(db)
    issuer_id = config.issuer_id
    if not issuer_id:
        raise ValueError("Issuer ID is not configured")
    return issuer_id


def _normalize_or_generate_dpp_id(dpp_id: str | None, issuer_id: str) -> str:
    if dpp_id is None:
        return _generate_dpp_id(issuer_id)

    normalized = dpp_id.strip()
    _validate_dpp_id_owned_by_issuer(normalized, issuer_id)
    return normalized


def _generate_dpp_id(issuer_id: str) -> str:
    return f"{issuer_id}{DPP_ID_ISSUER_SEPARATOR}{uuid.uuid4()}"


def _is_dpp_id_owned_by_issuer(dpp_id: str, issuer_id: str) -> bool:
    return dpp_id.startswith(f"{issuer_id}{DPP_ID_ISSUER_SEPARATOR}")


def _validate_dpp_id_owned_by_issuer(dpp_id: str, issuer_id: str) -> None:
    if not _is_dpp_id_owned_by_issuer(dpp_id, issuer_id):
        expected_prefix = f"{issuer_id}{DPP_ID_ISSUER_SEPARATOR}"
        raise ValueError(f"DPP ID must start with issuer ID followed by '-': {expected_prefix}")


def _build_revision_doc(
        dpp_id: str,
        version: int,
        schema_version: DppRevisionSchemaDTO,
        validated_payload: dict,
        payload_hash: str,
        created_at: datetime,
) -> dict:
    return {
        "dpp_id": dpp_id,
        "dpp_version": version,
        "schema": {
            "subject_type": schema_version.subject_type,
            "major_version": schema_version.major_version,
            "minor_version": schema_version.minor_version,
        },
        "dpp_document": validated_payload,
        "hashed_document": payload_hash,
        "created_at": created_at,
    }


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


def _cached_doc_to_response(doc: dict) -> DppRevisionResponseDTO:
    return DppRevisionResponseDTO(
        dpp_id=doc["dpp_id"],
        version=doc["dpp_version"],
        schema_version=DppRevisionSchemaDTO(
            subject_type=doc["schema_subject_type"],
            major_version=doc["schema_major_version"],
            minor_version=doc["schema_minor_version"],
        ),
        dpp_payload=doc["dpp_document"],
        payload_hash=doc["hashed_document"],
        created_at=doc["created_at"],
    )
