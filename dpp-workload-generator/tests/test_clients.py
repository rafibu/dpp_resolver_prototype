import json
import pytest
import re
from datetime import datetime

from workload.clients import PlatformClient, ResolverClient, IssueDppSpec, DppSchemaVersion, DppResponse, \
    DppNotFoundError, WorkloadError, build_predicate_query_params
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
async def test_platform_predicate_query_uses_java_compatible_get_parameters(httpx_mock, platform_info):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"^http://platform-a:8082/query/predicate(?:\\?.*)?$"),
        status_code=200,
        json={"result_mode": "COUNT", "execution_mode": "INDEXED", "platform_id": "platform-a", "count": 2},
    )

    async with PlatformClient(platform_info) as client:
        execution = await client.query_predicate({
            "result_mode": "COUNT",
            "execution_mode": "INDEXED",
            "subject_types": ["pv_module", "battery_pack"],
            "filters": [
                {"path": "production_country", "operator": "IN", "value": ["CH", "DE"]},
                {"path": "contains_lead", "operator": "EQ", "value": True},
            ],
        })

    request = httpx_mock.get_requests()[0]
    assert execution.status_code == 200
    assert execution.response["count"] == 2
    assert request.method == "GET"
    assert request.url.params.get("resultMode") == "COUNT"
    assert request.url.params.get("executionMode") == "INDEXED"
    assert request.url.params.get_list("subjectTypes") == ["pv_module", "battery_pack"]
    assert request.url.params.get_list("filters[0].value") == ["CH", "DE"]
    assert request.url.params.get("filters[1].value") == "true"


def test_predicate_query_params_omit_subject_types_for_all_type_query():
    params = build_predicate_query_params({
        "result_mode": "COUNT",
        "execution_mode": "INDEXED",
        "filters": [],
    })

    assert ("resultMode", "COUNT") in params
    assert not any(key == "subjectTypes" for key, _ in params)


@pytest.mark.asyncio
async def test_platform_traverse_query_uses_flattened_java_get_parameters(httpx_mock, platform_info):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"^http://platform-a:8082/query/traverse(?:\?.*)?$"),
        status_code=200,
        json={
            "platform_id": "platform-a",
            "subject_type": "component",
            "dpp_id": "issuerA-component-1",
            "matches": [],
        },
    )

    async with PlatformClient(platform_info) as client:
        execution = await client.query_traverse({
            "execution_mode": "ON_DEMAND",
            "subject_type": "component",
            "dpp_id": "issuerA-component-1",
            "revision_number": 3,
            "sources": [{
                "subject_type": "pv_module",
                "reference_paths": ["components.primary_component", "components.connector"],
            }],
        })

    request = httpx_mock.get_requests()[0]
    assert execution.status_code == 200
    assert request.method == "GET"
    assert request.url.params.get("executionMode") == "ON_DEMAND"
    assert request.url.params.get("subjectType") == "component"
    assert request.url.params.get("dppId") == "issuerA-component-1"
    assert request.url.params.get("revisionNumber") == "3"
    assert request.url.params.get("sources[0].subjectType") == "pv_module"
    assert request.url.params.get("sources[0].referencePaths[1]") == "components.connector"


@pytest.mark.asyncio
async def test_platform_import_revisions_replays_when_admin_endpoint_is_missing(httpx_mock, platform_info):
    schema_version = DppSchemaVersion(subject_type="pv_module", major_version=1, minor_version=0)
    revision_1 = DppResponse(
        dpp_id="issuerA-pv-001",
        version=1,
        schema_version=schema_version,
        dpp_payload={"foo": "one"},
        payload_hash="hash-one",
        created_at=datetime.fromisoformat("2026-05-03T12:00:00+00:00"),
    )
    revision_2 = DppResponse(
        dpp_id="issuerA-pv-001",
        version=2,
        schema_version=schema_version,
        dpp_payload={"foo": "two"},
        payload_hash="hash-two",
        created_at=datetime.fromisoformat("2026-05-03T13:00:00+00:00"),
    )

    httpx_mock.add_response(
        method="POST",
        url="http://platform-a:8082/admin/import-revisions",
        status_code=404,
    )
    httpx_mock.add_response(
        method="POST",
        url="http://platform-a:8082/dpps/issue",
        status_code=201,
        json=revision_1.model_dump(mode="json"),
    )
    httpx_mock.add_response(
        method="POST",
        url="http://platform-a:8082/dpps/issuerA-pv-001/revise",
        status_code=201,
        json=revision_2.model_dump(mode="json"),
    )

    async with PlatformClient(platform_info) as client:
        await client.import_revisions([revision_2, revision_1])

    requests = httpx_mock.get_requests()
    assert [str(request.url) for request in requests] == [
        "http://platform-a:8082/admin/import-revisions",
        "http://platform-a:8082/dpps/issue",
        "http://platform-a:8082/dpps/issuerA-pv-001/revise",
    ]
    assert json.loads(requests[1].content) == {
        "dpp_id": "issuerA-pv-001",
        "schema_version": {"subject_type": "pv_module", "major_version": 1, "minor_version": 0},
        "dpp_payload": {"foo": "one"},
    }
    assert json.loads(requests[2].content) == {
        "version": 2,
        "schema_version": {"subject_type": "pv_module", "major_version": 1, "minor_version": 0},
        "dpp_payload": {"foo": "two"},
    }


@pytest.mark.asyncio
async def test_platform_import_revisions_rejects_public_replay_for_different_issuer(httpx_mock, platform_info):
    revision = DppResponse(
        dpp_id="issuerB-pv-001",
        version=1,
        schema_version=DppSchemaVersion(subject_type="pv_module", major_version=1, minor_version=0),
        dpp_payload={"foo": "one"},
        payload_hash="hash-one",
        created_at=datetime.fromisoformat("2026-05-03T12:00:00+00:00"),
    )
    httpx_mock.add_response(
        method="POST",
        url="http://platform-a:8082/admin/import-revisions",
        status_code=404,
    )

    async with PlatformClient(platform_info) as client:
        with pytest.raises(WorkloadError, match="public replay cannot preserve source DPP ID"):
            await client.import_revisions([revision])

    assert [str(request.url) for request in httpx_mock.get_requests()] == [
        "http://platform-a:8082/admin/import-revisions",
    ]

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
async def test_resolver_ensure_platform_anchor_registers_alias(httpx_mock, platform_info):
    resolver_url = "http://resolver:8081"
    httpx_mock.add_response(
        method="GET",
        url=f"{resolver_url}/admin/platforms",
        status_code=200,
        json=[],
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{resolver_url}/admin/platforms/register",
        status_code=201,
    )

    async with ResolverClient(resolver_url) as client:
        await client.ensure_platform_anchor(platform_info, "issuerA_s1_origin_anchor", ["s1_inverter"])

    requests = httpx_mock.get_requests()
    assert [str(request.url) for request in requests] == [
        f"{resolver_url}/admin/platforms",
        f"{resolver_url}/admin/platforms/register",
    ]
    assert json.loads(requests[1].content) == {
        "platform": "platform-a",
        "resolution_url": "http://platform-a:8082/dpps/{dppId}",
        "issuer_id": "issuerA_s1_origin_anchor",
        "subject_types": ["s1_inverter"],
    }


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
