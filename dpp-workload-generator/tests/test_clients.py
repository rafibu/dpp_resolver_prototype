import pytest
from datetime import datetime
from workload.clients import PlatformClient, ResolverClient, IssueDppSpec, DppSchemaVersion, DppNotFoundError, \
    SchemaValidationError, CycleDetectedError
from workload.federation import PlatformInfo, PlatformStatus


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
        url="http://platform-a:8082/dpps/issue",
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
async def test_platform_revise_dpp(httpx_mock, platform_info):
    from workload.clients import ReviseDppSpec
    httpx_mock.add_response(
        method="POST",
        url="http://platform-a:8082/dpps/issuerA-pv-001/revise",
        json={
            "dpp_id": "issuerA-pv-001",
            "version": 2,
            "schema_version": {"subject_type": "pv_module", "major_version": 1, "minor_version": 0},
            "dpp_payload": {"foo": "updated"},
            "payload_hash": "hash456",
            "created_at": "2026-05-03T13:00:00Z"
        }
    )

    async with PlatformClient(platform_info) as client:
        spec = ReviseDppSpec(
            schema_version=DppSchemaVersion(subject_type="pv_module", major_version=1, minor_version=0),
            dpp_payload={"foo": "updated"}
        )
        resp = await client.revise_dpp("issuerA-pv-001", spec)
        assert resp.dpp_id == "issuerA-pv-001"
        assert resp.version == 2

@pytest.mark.asyncio
async def test_platform_not_found(httpx_mock, platform_info):
    httpx_mock.add_response(method="GET", url="http://platform-a:8082/dpps/missing", status_code=404)
    async with PlatformClient(platform_info) as client:
        with pytest.raises(DppNotFoundError):
            await client.get_revision("missing")

@pytest.mark.asyncio
async def test_resolver_ensure_subject_type_creates(httpx_mock):
    resolver_url = "http://resolver:8081"
    httpx_mock.add_response(method="POST", url=f"{resolver_url}/admin/subject-types", status_code=201)

    async with ResolverClient(resolver_url) as client:
        await client.ensure_subject_type("new_type")


@pytest.mark.asyncio
async def test_resolver_ensure_subject_type_idempotent(httpx_mock):
    resolver_url = "http://resolver:8081"
    # 409 Conflict (already exists) must be swallowed silently
    httpx_mock.add_response(method="POST", url=f"{resolver_url}/admin/subject-types", status_code=409)

    async with ResolverClient(resolver_url) as client:
        await client.ensure_subject_type("existing_type")


@pytest.mark.asyncio
async def test_resolver_ensure_subject_type_400_swallowed(httpx_mock):
    resolver_url = "http://resolver:8081"
    # Resolver may return 400 for duplicates in some versions; treat as harmless
    httpx_mock.add_response(method="POST", url=f"{resolver_url}/admin/subject-types", status_code=400)

    async with ResolverClient(resolver_url) as client:
        await client.ensure_subject_type("some_type")


@pytest.mark.asyncio
async def test_resolver_publish_schema(httpx_mock):
    resolver_url = "http://resolver:8081"
    # GET-first check: 404 means not yet published, then POST succeeds
    httpx_mock.add_response(method="GET", url=f"{resolver_url}/schemas/pv_module/1/0", status_code=404)
    httpx_mock.add_response(method="POST", url=f"{resolver_url}/schemas", status_code=201)

    async with ResolverClient(resolver_url) as client:
        await client.publish_schema("pv_module", 1, 0, {"type": "object"})


@pytest.mark.asyncio
async def test_resolver_publish_schema_idempotent(httpx_mock):
    resolver_url = "http://resolver:8081"
    # GET returns 200 (already exists) — no POST should be made
    httpx_mock.add_response(
        method="GET", url=f"{resolver_url}/schemas/pv_module/1/0", status_code=200,
        json={"subjectType": "pv_module", "majorVersion": 1, "minorVersion": 0, "schemaDocument": {}}
    )

    async with ResolverClient(resolver_url) as client:
        await client.publish_schema("pv_module", 1, 0, {"type": "object"})
        # No POST registered — if one is made the test will fail

@pytest.mark.asyncio
async def test_ensure_platform_route_adds_missing_subject_type(httpx_mock, platform_info):
    resolver_url = "http://resolver:8081"
    internal_template = "http://dpp-platform-a:8080/dpps/{dppId}"
    # Existing mapping registered by the Factory: one subject type, internal-URL template.
    httpx_mock.add_response(
        method="GET", url=f"{resolver_url}/admin/platforms", status_code=200,
        json=[{"platform": "platform-a", "issuer_id": "issuerA",
               "resolution_url": internal_template, "subject_types": ["pv_module"]}]
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{resolver_url}/admin/platforms/issuerA/subject-types/link_1",
        status_code=200,
    )

    async with ResolverClient(resolver_url) as client:
        await client.ensure_platform_route(platform_info, "link_1")

    post = [r for r in httpx_mock.get_requests() if r.method == "POST"][-1]
    assert str(post.url) == f"{resolver_url}/admin/platforms/issuerA/subject-types/link_1"
    assert post.content == b""


@pytest.mark.asyncio
async def test_ensure_platform_route_idempotent(httpx_mock, platform_info):
    resolver_url = "http://resolver:8081"
    # Subject type already declared: only the GET happens, no POST.
    httpx_mock.add_response(
        method="GET", url=f"{resolver_url}/admin/platforms", status_code=200,
        json=[{"platform": "platform-a", "issuer_id": "issuerA",
               "resolution_url": "http://dpp-platform-a:8080/dpps/{dppId}",
               "subject_types": ["pv_module"]}]
    )

    async with ResolverClient(resolver_url) as client:
        await client.ensure_platform_route(platform_info, "pv_module")

    assert all(r.method != "POST" for r in httpx_mock.get_requests())


@pytest.mark.asyncio
async def test_resolver_resolve(httpx_mock):
    resolver_url = "http://resolver:8081"
    httpx_mock.add_response(
        method="GET", 
        url=f"{resolver_url}/pv_module/issuerA-pv-001", 
        status_code=302,
        headers={"Location": "http://platform-a:8082/dpps/issuerA-pv-001"}
    )

    async with ResolverClient(resolver_url) as client:
        url = await client.resolve("pv_module", "issuerA-pv-001")
        assert url == "http://platform-a:8082/dpps/issuerA-pv-001"
        assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_resolver_resolve_revision_rewrites_internal_redirect(httpx_mock):
    resolver_url = "http://resolver:8081"
    httpx_mock.add_response(
        method="GET",
        url=f"{resolver_url}/pv_module/issuerA-pv-001/1",
        status_code=302,
        headers={"Location": "http://dpp-platform-a:8080/dpps/issuerA-pv-001/1"},
    )
    httpx_mock.add_response(
        method="GET",
        url="http://platform-a:8082/dpps/issuerA-pv-001/1",
        status_code=200,
        json={"dpp_id": "issuerA-pv-001"},
    )

    async with ResolverClient(resolver_url) as client:
        response = await client.resolve_revision(
            "pv_module",
            "issuerA-pv-001",
            version=1,
            redirect_base_url="http://platform-a:8082",
        )

    assert response.json() == {"dpp_id": "issuerA-pv-001"}
    assert [str(request.url) for request in httpx_mock.get_requests()] == [
        f"{resolver_url}/pv_module/issuerA-pv-001/1",
        "http://platform-a:8082/dpps/issuerA-pv-001/1",
    ]


@pytest.mark.asyncio
async def test_resolver_resolve_revision_closure_uses_max_depth_query(httpx_mock):
    resolver_url = "http://resolver:8081"
    httpx_mock.add_response(
        method="GET",
        url=f"{resolver_url}/pv_module/issuerA-pv-001/1",
        status_code=302,
        headers={"Location": "http://dpp-platform-a:8080/dpps/issuerA-pv-001/1"},
    )
    httpx_mock.add_response(
        method="GET",
        url="http://platform-a:8082/dpps/issuerA-pv-001/1/closure?max_depth=2",
        status_code=200,
        json={"root": {"dpp_id": "issuerA-pv-001"}, "closure": []},
    )

    async with ResolverClient(resolver_url) as client:
        response = await client.resolve_revision_closure(
            "pv_module",
            "issuerA-pv-001",
            version=1,
            max_depth=2,
            redirect_base_url="http://platform-a:8082",
        )

    assert response.json()["root"]["dpp_id"] == "issuerA-pv-001"
    assert [str(request.url) for request in httpx_mock.get_requests()] == [
        f"{resolver_url}/pv_module/issuerA-pv-001/1",
        "http://platform-a:8082/dpps/issuerA-pv-001/1/closure?max_depth=2",
    ]

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
