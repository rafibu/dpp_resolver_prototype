"""Merge per-platform responses into one federation-level result.

The merger never inspects DPP payload semantics; it only combines the
platform-local responses according to the requested result mode (SELECT, COUNT,
SUM). It operates on the same :class:`PlatformQueryResult` objects produced by
the fan-out: for SUM it may demote a successful-but-malformed platform result to
FAILED, so the caller must recompute aggregate counts after merging.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .models import (
    CombinedQueryResult,
    FederatedPredicateQueryRequest,
    PlatformCallStatus,
    PlatformQueryResult,
    QueryResultMode,
)

# Candidate keys for the optional SELECT deduplication identity.
_DPP_ID_KEYS = ("logical_dpp_id", "dpp_id", "dppId", "logicalDppId", "id")
_REVISION_KEYS = ("revision", "version", "revision_number", "revisionNumber")


def merge_results(
    request: FederatedPredicateQueryRequest,
    platform_results: list[PlatformQueryResult],
) -> CombinedQueryResult:
    """Produce a :class:`CombinedQueryResult` from per-platform results."""
    combined = CombinedQueryResult(
        result_mode=request.result_mode,
        execution_mode=request.execution_mode,
    )
    successful = [r for r in platform_results if r.status is PlatformCallStatus.SUCCESS]

    if request.result_mode is QueryResultMode.SELECT:
        _merge_select(successful, combined)
    elif request.result_mode is QueryResultMode.COUNT:
        _merge_count(successful, combined)
    else:  # SUM
        _merge_sum(successful, combined)

    return combined


# --------------------------------------------------------------------------- #
# SELECT
# --------------------------------------------------------------------------- #
def _merge_select(
    successful: list[PlatformQueryResult], combined: CombinedQueryResult
) -> None:
    enriched: list[Any] = []
    seen_keys: set[tuple[str, str, str]] = set()
    dedup_disabled = False

    for result in successful:
        response = result.response
        if response is None:
            continue
        combined.source_platforms.append(result.platform_id)
        platform_id = response.platform_id or result.platform_id
        matches = _as_match_list(response.matches, combined)

        for match in matches:
            match = _enrich(match, platform_id)
            key = _dedup_key(match, platform_id)
            if key is None:
                dedup_disabled = True
                enriched.append(match)
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)
            enriched.append(match)

    if dedup_disabled:
        combined.warnings.append(
            "Some matches lacked a logical DPP identity and revision number; "
            "those matches were not deduplicated."
        )

    combined.matches = enriched
    combined.count = len(enriched)


def _as_match_list(matches: Any, combined: CombinedQueryResult) -> list[Any]:
    if matches is None:
        return []
    if isinstance(matches, list):
        return matches
    combined.warnings.append(
        "A platform returned SELECT matches that were not a list; the value was wrapped."
    )
    return [matches]


def _enrich(match: Any, platform_id: str) -> Any:
    """Attach platform_id to a match dict if it is not already present."""
    if isinstance(match, dict) and "platform_id" not in match:
        enriched = dict(match)
        enriched["platform_id"] = platform_id
        return enriched
    return match


def _dedup_key(match: Any, platform_id: str) -> tuple[str, str, str] | None:
    if not isinstance(match, dict):
        return None
    dpp_id = _first_present(match, _DPP_ID_KEYS)
    revision = _first_present(match, _REVISION_KEYS)
    if dpp_id is None or revision is None:
        return None
    return (str(platform_id), str(dpp_id), str(revision))


def _first_present(match: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in match and match[key] is not None:
            return match[key]
    return None


# --------------------------------------------------------------------------- #
# COUNT
# --------------------------------------------------------------------------- #
def _merge_count(
    successful: list[PlatformQueryResult], combined: CombinedQueryResult
) -> None:
    total = 0
    for result in successful:
        response = result.response
        if response is None:
            continue
        combined.source_platforms.append(result.platform_id)
        total += response.count or 0
    combined.count = total


# --------------------------------------------------------------------------- #
# SUM
# --------------------------------------------------------------------------- #
def _merge_sum(
    successful: list[PlatformQueryResult], combined: CombinedQueryResult
) -> None:
    total = Decimal(0)
    for result in successful:
        response = result.response
        if response is None:
            continue

        aggregate = response.aggregate
        if aggregate is None:
            # A missing aggregate is only acceptable for an empty result set.
            if (response.count or 0) == 0 and not response.matches:
                combined.source_platforms.append(result.platform_id)
                continue
            result.status = PlatformCallStatus.FAILED
            result.error_message = (
                "Platform returned a non-empty SUM result without an aggregate value"
            )
            continue

        try:
            total += Decimal(aggregate)
        except (InvalidOperation, TypeError):
            result.status = PlatformCallStatus.FAILED
            result.error_message = f"Platform returned a non-numeric aggregate: {aggregate!r}"
            continue

        combined.source_platforms.append(result.platform_id)

    combined.aggregate = total
