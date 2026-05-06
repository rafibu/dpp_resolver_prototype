import asyncio
import json
from datetime import UTC, datetime

import pytest

from dpp_platform_factory.core.state import FactoryState, PlatformRecord, PlatformStatus, ResolverRecord


def _make_platform(platform_id: str = "platform-a", status: PlatformStatus = PlatformStatus.RUNNING) -> PlatformRecord:
    return PlatformRecord(
        platform_id=platform_id,
        stack="spring-postgres",
        issuer_id="issuerA",
        subject_types=["pv_module"],
        container_id="cid-1",
        db_container_id="cid-db-1",
        external_url="http://localhost:8081",
        internal_url="http://dpp-platform-a:8080",
        status=status,
        created_at=datetime.now(UTC),
    )


def _make_resolver() -> ResolverRecord:
    return ResolverRecord(
        container_id="res-cid",
        db_container_id="res-db-cid",
        external_url="http://localhost:8080",
        internal_url="http://dpp-resolver:8080",
        status=PlatformStatus.RUNNING,
        started_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Resolver operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_get_resolver():
    state = FactoryState()
    record = _make_resolver()
    await state.set_resolver(record)
    assert (await state.get_resolver()) is record


@pytest.mark.asyncio
async def test_resolver_starts_as_none():
    state = FactoryState()
    assert (await state.get_resolver()) is None


# ---------------------------------------------------------------------------
# Platform CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_get_platform():
    state = FactoryState()
    p = _make_platform("platform-a")
    await state.add_platform(p)
    result = await state.get_platform("platform-a")
    assert result is p


@pytest.mark.asyncio
async def test_get_missing_platform_returns_none():
    state = FactoryState()
    assert (await state.get_platform("does-not-exist")) is None


@pytest.mark.asyncio
async def test_remove_platform_returns_record():
    state = FactoryState()
    p = _make_platform()
    await state.add_platform(p)
    removed = await state.remove_platform("platform-a")
    assert removed is p
    assert (await state.get_platform("platform-a")) is None


@pytest.mark.asyncio
async def test_remove_missing_platform_returns_none():
    state = FactoryState()
    assert (await state.remove_platform("no-such")) is None


@pytest.mark.asyncio
async def test_update_status():
    state = FactoryState()
    await state.add_platform(_make_platform(status=PlatformStatus.RUNNING))
    await state.update_status("platform-a", PlatformStatus.PAUSED)
    p = await state.get_platform("platform-a")
    assert p.status == PlatformStatus.PAUSED


@pytest.mark.asyncio
async def test_update_status_missing_platform_is_noop():
    state = FactoryState()
    await state.update_status("no-such", PlatformStatus.PAUSED)  # should not raise


@pytest.mark.asyncio
async def test_list_platforms():
    state = FactoryState()
    await state.add_platform(_make_platform("platform-a"))
    await state.add_platform(_make_platform("platform-b"))
    platforms = await state.list_platforms()
    ids = {p.platform_id for p in platforms}
    assert ids == {"platform-a", "platform-b"}


@pytest.mark.asyncio
async def test_used_ports():
    state = FactoryState()
    p = _make_platform()
    p.external_url = "http://localhost:8081"
    await state.add_platform(p)
    ports = await state.used_ports()
    assert 8081 in ports


# ---------------------------------------------------------------------------
# Concurrent access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_add_platforms():
    state = FactoryState()

    async def add(i: int):
        await state.add_platform(_make_platform(f"platform-{i}"))

    await asyncio.gather(*[add(i) for i in range(10)])
    platforms = await state.list_platforms()
    assert len(platforms) == 10


@pytest.mark.asyncio
async def test_concurrent_status_updates():
    state = FactoryState()
    await state.add_platform(_make_platform("platform-a", PlatformStatus.RUNNING))

    async def flip(status: PlatformStatus):
        await state.update_status("platform-a", status)

    await asyncio.gather(
        flip(PlatformStatus.PAUSED),
        flip(PlatformStatus.RUNNING),
        flip(PlatformStatus.PAUSED),
    )
    p = await state.get_platform("platform-a")
    assert p.status in (PlatformStatus.RUNNING, PlatformStatus.PAUSED)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_to_dict_contains_resolver_and_platforms():
    state = FactoryState()
    await state.set_resolver(_make_resolver())
    await state.add_platform(_make_platform("platform-a"))
    d = state.to_dict()
    assert d["resolver"] is not None
    assert "platform-a" in d["platforms"]


@pytest.mark.asyncio
async def test_to_dict_resolver_none_when_not_set():
    state = FactoryState()
    d = state.to_dict()
    assert d["resolver"] is None


@pytest.mark.asyncio
async def test_to_json_is_valid_json():
    state = FactoryState()
    await state.add_platform(_make_platform())
    raw = state.to_json()
    parsed = json.loads(raw)
    assert "platforms" in parsed


@pytest.mark.asyncio
async def test_to_dict_datetimes_are_iso_strings():
    state = FactoryState()
    await state.add_platform(_make_platform())
    d = state.to_dict()
    created_at = d["platforms"]["platform-a"]["created_at"]
    assert isinstance(created_at, str)
    datetime.fromisoformat(created_at)


@pytest.mark.asyncio
async def test_to_dict_status_is_string():
    state = FactoryState()
    await state.add_platform(_make_platform())
    d = state.to_dict()
    assert d["platforms"]["platform-a"]["status"] == "RUNNING"
