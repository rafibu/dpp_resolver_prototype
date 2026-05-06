import pytest
from workload.clients import PlatformClient, ResolverClient, IssueDppSpec, DppSchemaVersion, DppNotFoundError, SchemaValidationError, CycleDetectedError
from workload.federation import PlatformInfo, PlatformStatus
from datetime import datetime

@pytest.fixture
def platform_info():
    return PlatformInfo(
        platform_id="platform-a",
        stack="java",
        issuer_id="issuerA",
        subject_types=["pv_module"],
        external_url="http://platform-a:8082",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now()
    )

@pytest.mark.asyncio
async def test_platform_issue_dpp(httpx_mock, platform_info):
    httpx_mock.add_response(
        method="POST",
        url="http://platform-a:8082/dpps",
        json={
            "dpp_id": "issuerA-pv-001",
            "version": 1,
            "schema_version": {"subject_type": "pv_module", "major_version": 1, "minor_version": 0},
            "dpp_payload": {"foo": "bar"},
            "payload_hash": "hash123",
            "created_at": "2026-05-03T12:00:00Z"
        }
    )

    async with PlatformClient(platform_info) as client:
        spec = IssueDppSpec(
            schema_version=DppSchemaVersion(subject_type="pv_module", major_version=1, minor_version=0),
            dpp_payload={"foo": "bar"}
        )
        resp = await client.issue_dpp(spec)
        assert resp.dpp_id == "issuerA-pv-001"
        assert resp.version == 1

@pytest.mark.asyncio
async def test_platform_not_found(httpx_mock, platform_info):
    httpx_mock.add_response(method="GET", url="http://platform-a:8082/dpps/missing", status_code=404)
    async with PlatformClient(platform_info) as client:
        with pytest.raises(DppNotFoundError):
            await client.get_revision("missing")

@pytest.mark.asyncio
async def test_resolver_publish_schema(httpx_mock):
    resolver_url = "http://resolver:8081"
    httpx_mock.add_response(method="POST", url=f"{resolver_url}/schemas", status_code=201)
    
    async with ResolverClient(resolver_url) as client:
        await client.publish_schema("pv_module", 1, 0, {"type": "object"})

@pytest.mark.asyncio
async def test_resolver_resolve(httpx_mock):
    resolver_url = "http://resolver:8081"
    # httpx-mock handles redirects if we add multiple responses or use a redirect response
    httpx_mock.add_response(
        method="GET", 
        url=f"{resolver_url}/pv_module/issuerA-pv-001", 
        status_code=302,
        headers={"Location": "http://platform-a:8082/dpps/issuerA-pv-001"}
    )
    httpx_mock.add_response(
        method="GET",
        url="http://platform-a:8082/dpps/issuerA-pv-001",
        status_code=200
    )

    async with ResolverClient(resolver_url) as client:
        url = await client.resolve("pv_module", "issuerA-pv-001")
        assert url == "http://platform-a:8082/dpps/issuerA-pv-001"

@pytest.mark.asyncio
async def test_retry_on_timeout(httpx_mock, platform_info):
    import httpx
    # First two fail with timeout, third succeeds
    httpx_mock.add_exception(httpx.TimeoutException("Timeout"), method="GET", url="http://platform-a:8082/schemas/pv/1/0")
    httpx_mock.add_exception(httpx.TimeoutException("Timeout"), method="GET", url="http://platform-a:8082/schemas/pv/1/0")
    httpx_mock.add_response(method="GET", url="http://platform-a:8082/schemas/pv/1/0", json={"type": "object"})

    async with PlatformClient(platform_info) as client:
        # We need to monkeypatch asyncio.sleep to not wait in tests
        import asyncio
        original_sleep = asyncio.sleep
        asyncio.sleep = lambda x: original_sleep(0)
        try:
            resp = await client.get_schema("pv", 1, 0)
            assert resp == {"type": "object"}
        finally:
            asyncio.sleep = original_sleep
