"""Resolver discovery client.

Fetches registered platform mappings from the resolver and normalizes them into
a unique list of :class:`PlatformMapping` objects. The resolver registry maps
*issuers* to platforms, so multiple entries may refer to the same platform; this
module deduplicates them so each platform is queried exactly once.
"""

from __future__ import annotations

import httpx
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .config import Config
from .models import PlatformMapping


class ResolverError(RuntimeError):
    """Raised when the resolver cannot be reached or returns an invalid shape."""


# Candidate keys tolerate both snake_case (current global config) and camelCase.
_PLATFORM_ID_KEYS = ("platform_id", "platformId", "platform", "platform_name", "platformName")
_BASE_URL_KEYS = ("base_url", "baseUrl")
_RESOLUTION_URL_KEYS = ("resolution_url", "resolutionUrl")


async def get_platforms(client: httpx.AsyncClient, config: Config) -> list[PlatformMapping]:
    """Return the unique platforms registered with the resolver.

    Raises :class:`ResolverError` on transport errors, non-2xx responses, or an
    unparseable body. Individual malformed entries are skipped rather than
    failing the whole discovery.
    """
    url = config.resolver_platforms_url
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ResolverError(f"Failed to fetch platforms from resolver at {url}: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ResolverError(f"Resolver returned non-JSON body from {url}") from exc

    entries = _as_entry_list(payload)
    return _normalize_and_dedupe(entries)


def _as_entry_list(payload: Any) -> list[dict[str, Any]]:
    """Accept either a bare array or a wrapped ``{"platforms": [...]}`` object."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("platforms"), list):
        items = payload["platforms"]
    else:
        raise ResolverError("Resolver response is not a list of platform mappings")
    return [item for item in items if isinstance(item, dict)]


def _normalize_and_dedupe(entries: list[dict[str, Any]]) -> list[PlatformMapping]:
    seen: set[str] = set()
    platforms: list[PlatformMapping] = []
    for entry in entries:
        base_url = _extract_base_url(entry)
        if base_url is None:
            continue
        platform_id = _extract_platform_id(entry) or base_url
        # Query each distinct platform once. base_url is the actual call target,
        # so it is the canonical dedup key; platform_id is used when available.
        dedup_key = base_url
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        platforms.append(PlatformMapping(platform_id=platform_id, base_url=base_url))
    return platforms


def _extract_platform_id(entry: dict[str, Any]) -> str | None:
    for key in _PLATFORM_ID_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _extract_base_url(entry: dict[str, Any]) -> str | None:
    """Resolve a platform base URL (scheme://host[:port]) from a registry entry.

    Prefers an explicit ``base_url``; otherwise derives the origin from the
    resolver's ``resolution_url`` template (e.g. ``http://platform-a:8081/dpps/{dppId}``
    -> ``http://platform-a:8081``).
    """
    for key in _BASE_URL_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.rstrip("/")

    for key in _RESOLUTION_URL_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            origin = _origin_of(value)
            if origin:
                return origin
    return None


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
