import json
from datetime import UTC, datetime

import pytest

from dpp_platform_factory.core.state import PlatformRecord, PlatformStatus
from dpp_platform_factory.infrastructure.resolver_client import ResolverClient


def _make_platform(
    platform_id: str = "platform-a",
    issuer_id: str = "issuerA",
    subject_types: list[str] | None = None,
) -> PlatformRecord:
    return PlatformRecord(
        platform_id=platform_id,
        stack="spring-postgres",
        issuer_id=issuer_id,
        subject_types=subject_types or ["pv_module"],
        container_id="cid",
        db_container_id="db-cid",
        external_url="http://localhost:8081",
        internal_url=f"http://dpp-{platform_id}:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(UTC),
    )

@pytest.mark.asyncio
async def test_register_platform_posts_to_register_url(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/register", status_code=201)

    await resolver.register_platform(_make_platform())

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert str(requests[0].url) == "http://resolver:8080/admin/platforms/register"

@pytest.mark.asyncio
async def test_register_platform_sends_correct_body(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/register", status_code=201)

    await resolver.register_platform(_make_platform("platform-a"))

    body = json.loads(httpx_mock.get_request().content)
    assert body["platform"] == "platform-a"
    assert body["issuer_id"] == "issuerA"
    # Internal Docker URL template so platform containers can follow the resolver redirect (I7).
    assert body["resolution_url"] == "http://dpp-platform-a:8080/dpps/{dppId}"
    assert "pv_module" in body["subject_types"]

@pytest.mark.asyncio
async def test_register_platform_accepts_201(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/register", status_code=201)

    await resolver.register_platform(_make_platform())  # no exception

@pytest.mark.asyncio
async def test_register_platform_rejects_200_because_register_is_not_upsert(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/register", status_code=200)

    with pytest.raises(RuntimeError):
        await resolver.register_platform(_make_platform())

@pytest.mark.asyncio
async def test_register_platform_raises_on_server_error(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/register", status_code=500, text="internal error")

    with pytest.raises(RuntimeError, match="platform-a"):
        await resolver.register_platform(_make_platform())

@pytest.mark.asyncio
async def test_register_platform_raises_on_400(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/register", status_code=400, text="bad request")

    with pytest.raises(RuntimeError):
        await resolver.register_platform(_make_platform())

@pytest.mark.asyncio
async def test_trailing_slash_stripped(httpx_mock):
    resolver = ResolverClient("http://resolver:8080/")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/register", status_code=201)

    await resolver.register_platform(_make_platform())

    assert str(httpx_mock.get_request().url) == "http://resolver:8080/admin/platforms/register"

@pytest.mark.asyncio
async def test_migrate_platform_posts_to_migrate_url_and_body(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/issuerA/migrate", status_code=200)

    await resolver.migrate_platform("issuerA", _make_platform("platform-b", "issuerB", ["inverter"]))

    request = httpx_mock.get_request()
    assert str(request.url) == "http://resolver:8080/admin/platforms/issuerA/migrate"
    body = json.loads(request.content)
    assert body["platform"] == "platform-b"
    assert body["new_resolution_url"] == "http://dpp-platform-b:8080/dpps/{dppId}"
    assert "issuer_id" not in body
    assert "subject_types" not in body

@pytest.mark.asyncio
async def test_migrate_platform_accepts_200(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/admin/platforms/issuerA/migrate", status_code=200)

    await resolver.migrate_platform("issuerA", _make_platform("platform-b", "issuerB"))

@pytest.mark.asyncio
async def test_migrate_platform_raises_on_400(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(
        url="http://resolver:8080/admin/platforms/issuerA/migrate",
        status_code=400,
        text="bad request",
    )

    with pytest.raises(RuntimeError, match="issuerA"):
        await resolver.migrate_platform("issuerA", _make_platform("platform-b", "issuerB"))

@pytest.mark.asyncio
async def test_publish_schema_posts_correct_dto(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/schemas", status_code=201)

    schema_doc = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://schemas.dpp.eu/battery/1.0",
        "type": "object",
    }
    await resolver.publish_schema("battery", 1, 0, schema_doc)

    body = json.loads(httpx_mock.get_request().content)
    assert body["subject_type"] == "battery"
    assert body["major_version"] == 1
    assert body["minor_version"] == 0
    assert body["schema_document"] == schema_doc

@pytest.mark.asyncio
async def test_publish_schema_raises_on_server_error(httpx_mock):
    resolver = ResolverClient("http://resolver:8080")
    httpx_mock.add_response(url="http://resolver:8080/schemas", status_code=422, text="cycle detected")

    with pytest.raises(Exception):
        await resolver.publish_schema("battery", 1, 0, {})
