from collections import deque

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from .exceptions import DppCycleDetectedException
from .models import DependencyType
from .reference_extractor import extract_references

logger = structlog.get_logger()

_MAX_ROUNDS = 3


async def detect_cycles(
        db: AsyncIOMotorDatabase,
        subject_type: str,
        dpp_id: str,
        version: int,
        initial_payload: dict,
        issuer_id: str,
) -> None:
    """BFS hard-dependency cycle detection, bounded to _MAX_ROUNDS. Invariant I6."""
    candidate_key = f"{subject_type}/{dpp_id}"

    hard_refs = [
        r for r in extract_references(initial_payload)
        if r.dependency_type == DependencyType.HARD
    ]

    if not hard_refs:
        return

    queue: deque[list[str]] = deque()
    for ref in hard_refs:
        queue.append([candidate_key, f"{ref.subject_type}/{ref.dpp_id}"])

    visited: set[str] = {candidate_key}
    current_round_count = len(queue)
    next_round_count = 0
    round_num = 0

    while queue and round_num < _MAX_ROUNDS:
        path = queue.popleft()
        current_node = path[-1]

        if current_node == candidate_key:
            raise DppCycleDetectedException(path)

        if current_node not in visited:
            visited.add(current_node)
            refs = await _fetch_hard_references(db, current_node, issuer_id)
            for ref in refs:
                next_key = f"{ref.subject_type}/{ref.dpp_id}"
                queue.append(path + [next_key])
                next_round_count += 1

        current_round_count -= 1
        if current_round_count == 0:
            round_num += 1
            current_round_count = next_round_count
            next_round_count = 0


async def _fetch_hard_references(
        db: AsyncIOMotorDatabase, node_key: str, issuer_id: str
) -> list:
    parts = node_key.split("/", 1)
    if len(parts) != 2:
        return []
    subject_type, dpp_id = parts

    payload = await _get_payload(db, subject_type, dpp_id, issuer_id)
    if payload is None:
        return []

    return [
        r for r in extract_references(payload)
        if r.dependency_type == DependencyType.HARD
    ]


async def _get_payload(
        db: AsyncIOMotorDatabase,
        subject_type: str,
        dpp_id: str,
        issuer_id: str,
) -> dict | None:
    if dpp_id.startswith(issuer_id):
        doc = await db.dpp_revisions.find_one(
            {"dpp_id": dpp_id},
            {"dpp_document": 1, "_id": 0},
            sort=[("dpp_version", -1)],
        )
        return doc["dpp_document"] if doc else None

    cached = await db.referenced_dpp_revisions.find_one(
        {"dpp_id": dpp_id},
        {"dpp_document": 1, "_id": 0},
        sort=[("dpp_version", -1)],
    )
    if cached:
        return cached["dpp_document"]

    # Resolve via Resolver as last resort (import here to avoid circular)
    from ..schemas.resolver_connector import resolve_dpp_revision

    try:
        response = await resolve_dpp_revision(db, subject_type, dpp_id, version=None)
        if response:
            return response.dpp_payload
    except Exception:
        logger.warning("cycle_detection_resolve_failed", dpp_id=dpp_id)

    return None
