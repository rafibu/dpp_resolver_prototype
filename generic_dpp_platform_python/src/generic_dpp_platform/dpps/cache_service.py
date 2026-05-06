from datetime import UTC, datetime, timedelta

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from .utils import verify_hash_integrity

logger = structlog.get_logger()

_TTL_DAYS = 7


async def get_cached_revision(
    db: AsyncIOMotorDatabase, dpp_id: str, version: int
) -> dict | None:
    """Return cached external revision or None if missing, stale, or corrupted. Invariant I4."""
    doc = await db.referenced_dpp_revisions.find_one(
        {"dpp_id": dpp_id, "dpp_version": version}, {"_id": 0}
    )
    if doc is None:
        return None

    fetched_at: datetime = doc["fetched_at"]
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)

    if datetime.now(UTC) - fetched_at > timedelta(days=_TTL_DAYS):
        logger.info("cache_entry_stale", dpp_id=dpp_id, version=version)
        await db.referenced_dpp_revisions.delete_one({"dpp_id": dpp_id, "dpp_version": version})
        return None

    if not verify_hash_integrity(doc["dpp_document"], doc["hashed_document"]):
        logger.error("cache_hash_mismatch", dpp_id=dpp_id, version=version)
        await db.referenced_dpp_revisions.delete_one({"dpp_id": dpp_id, "dpp_version": version})
        return None

    return doc


async def cache_revision(db: AsyncIOMotorDatabase, revision: dict) -> None:
    revision = {**revision, "fetched_at": datetime.now(UTC)}
    await db.referenced_dpp_revisions.replace_one(
        {"dpp_id": revision["dpp_id"], "dpp_version": revision["dpp_version"]},
        revision,
        upsert=True,
    )
