import httpx
import pytest
from datetime import UTC, datetime

from dpp_platform_factory.core.scenario_service import ScenarioService
from dpp_platform_factory.core.state import PlatformRecord, PlatformStatus


def _platform() -> PlatformRecord:
    return PlatformRecord(
        platform_id="platform-a",
        stack="spring-postgres",
        issuer_id="issuerA",
        subject_types=["pv_module"],
        container_id="platform-container",
        db_container_id="platform-db",
        external_url="http://localhost:8081",
        internal_url="http://dpp-platform-a:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(UTC),
    )


def _response(status_code: int, url: str, body: str = "") -> httpx.Response:
    return httpx.Response(
        status_code,
        text=body,
        request=httpx.Request("POST", url),
    )


@pytest.mark.asyncio
async def test_cache_subjects_restores_platform_subject_type_before_cache(monkeypatch):
    service = ScenarioService(None, None, None)
    calls = []

    async def post_raw(url: str, body: dict) -> httpx.Response:
        calls.append(("subject-type", url, body))
        return _response(201, url)

    async def post_json(url: str, body: dict) -> dict:
        calls.append(("cache-schema", url, body))
        return {}

    monkeypatch.setattr(service, "_post_raw", post_raw)
    monkeypatch.setattr(service, "_post_json", post_json)

    await service._cache_subjects(_platform(), ["pv_module"])

    assert calls == [
        (
            "subject-type",
            "http://dpp-platform-a:8080/admin/subject-types",
            {"name": "pv_module", "description": "Pv Module"},
        ),
        ("cache-schema", "http://dpp-platform-a:8080/schemas/pv_module/cacheSchema", {}),
    ]


@pytest.mark.asyncio
async def test_cache_subjects_accepts_duplicate_subject_type_response(monkeypatch):
    service = ScenarioService(None, None, None)
    cache_calls = []

    async def post_raw(url: str, body: dict) -> httpx.Response:
        return _response(400, url, "Subject type with name pv_module already exists")

    async def post_json(url: str, body: dict) -> dict:
        cache_calls.append((url, body))
        return {}

    monkeypatch.setattr(service, "_post_raw", post_raw)
    monkeypatch.setattr(service, "_post_json", post_json)

    await service._cache_subjects(_platform(), ["pv_module"])

    assert cache_calls == [("http://dpp-platform-a:8080/schemas/pv_module/cacheSchema", {})]


@pytest.mark.asyncio
async def test_cache_subjects_rejects_unexpected_subject_type_error(monkeypatch):
    service = ScenarioService(None, None, None)

    async def post_raw(url: str, body: dict) -> httpx.Response:
        return _response(400, url, "validation failed")

    async def post_json(url: str, body: dict) -> dict:
        return {}

    monkeypatch.setattr(service, "_post_raw", post_raw)
    monkeypatch.setattr(service, "_post_json", post_json)

    with pytest.raises(httpx.HTTPStatusError):
        await service._cache_subjects(_platform(), ["pv_module"])
