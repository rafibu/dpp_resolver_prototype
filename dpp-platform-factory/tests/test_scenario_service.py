import httpx
import pytest
from datetime import UTC, datetime
from types import SimpleNamespace

from dpp_platform_factory.core.scenario_service import SCENARIO_IDS, ScenarioService, _build_report
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


def test_scenario_ids_include_s5():
    assert SCENARIO_IDS == ("s1", "s2", "s3", "s4", "s5")


@pytest.mark.asyncio
async def test_s4_runs_the_query_evaluation_workload(monkeypatch):
    service = ScenarioService(None, None, None)
    observations: list[str] = []
    calls: list[str] = []

    async def checked(name, action):
        calls.append(name)
        return await action()

    class Result:
        success = True
        report_md = "# Scenario S4: Query Execution"
        observations = ("Run ID: s4-test",)
        steps = (
            type("Step", (), {"name": "Prepare deterministic S4 dataset", "status": "passed", "error": None})(),
        )

    async def execute_workload():
        calls.append("query-workload")
        return Result()

    monkeypatch.setattr(service, "_execute_s4_workload", execute_workload)

    report = await service._run_s4(checked, observations)

    assert calls == ["Execute S4 query evaluation workload", "query-workload", "Prepare deterministic S4 dataset"]
    assert observations == ["Run ID: s4-test"]
    assert report == "# Scenario S4: Query Execution"


def test_s4_and_s5_report_titles_have_the_canonical_meanings():
    assert _build_report("s4", "passed", 1, [], []).startswith("# S4: Query Execution")
    assert _build_report("s5", "passed", 1, [], []).startswith(
        "# S5: Offline Validation After Platform Unavailability"
    )


@pytest.mark.asyncio
async def test_run_s4_returns_the_workload_markdown_and_steps(monkeypatch):
    service = ScenarioService(None, None, None)
    result = SimpleNamespace(
        success=True,
        report_md="# Scenario S4: Query Execution\n\n- Status: `passed`",
        observations=("Run ID: s4-test",),
        steps=(SimpleNamespace(name="Compare INDEXED and ON_DEMAND query results", status="passed", error=None),),
    )

    async def execute_workload():
        return result

    monkeypatch.setattr(service, "_execute_s4_workload", execute_workload)

    status = await service.run("s4")

    assert status.status == "passed"
    assert status.report_md == result.report_md
    assert [step.name for step in status.steps] == [
        "Execute S4 query evaluation workload",
        "Compare INDEXED and ON_DEMAND query results",
    ]


@pytest.mark.asyncio
async def test_run_s4_exposes_a_failed_workload_as_failed_status(monkeypatch):
    service = ScenarioService(None, None, None)
    result = SimpleNamespace(
        success=False,
        report_md="# Scenario S4: Query Execution\n\n- Status: `failed`",
        observations=("A query pair was non-equivalent.",),
        steps=(),
    )

    async def execute_workload():
        return result

    monkeypatch.setattr(service, "_execute_s4_workload", execute_workload)

    status = await service.run("s4")

    assert status.status == "failed"
    assert status.report_md == result.report_md
    assert status.steps[-1].name == "Verify S4 query equivalence"
    assert status.steps[-1].status == "failed"
    assert status.steps[-1].error == "S4 query evaluation reported failed checks"


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


@pytest.mark.asyncio
async def test_ensure_platform_anchor_registers_alias(monkeypatch):
    service = ScenarioService(None, None, None)
    calls = []

    async def get_json(url: str):
        calls.append(("get", url, None))
        return []

    async def post_json(url: str, body) -> dict:
        calls.append(("post", url, body))
        return {}

    monkeypatch.setattr(service, "_get_json", get_json)
    monkeypatch.setattr(service, "_post_json", post_json)

    await service._ensure_platform_anchor(
        "http://resolver:8080",
        _platform(),
        "issuerA_s1_origin_anchor",
        ["s1_inverter"],
    )

    assert calls == [
        ("get", "http://resolver:8080/admin/platforms", None),
        (
            "post",
            "http://resolver:8080/admin/platforms/register",
            {
                "platform": "platform-a",
                "resolution_url": "http://dpp-platform-a:8080/dpps/{dppId}",
                "issuer_id": "issuerA_s1_origin_anchor",
                "subject_types": ["s1_inverter"],
            },
        ),
    ]


@pytest.mark.asyncio
async def test_import_revisions_replays_when_admin_endpoint_is_missing(monkeypatch):
    service = ScenarioService(None, None, None)
    calls = []
    schema_version = {
        "subject_type": "pv_module",
        "major_version": 1,
        "minor_version": 0,
    }
    revision_1 = {
        "dpp_id": "issuerA-pv-001",
        "version": 1,
        "schema_version": schema_version,
        "dpp_payload": {"foo": "one"},
        "payload_hash": "hash-one",
    }
    revision_2 = {
        "dpp_id": "issuerA-pv-001",
        "version": 2,
        "schema_version": schema_version,
        "dpp_payload": {"foo": "two"},
        "payload_hash": "hash-two",
    }

    async def post_raw(url: str, body) -> httpx.Response:
        calls.append(("admin-import", url, body))
        return _response(404, url)

    async def post_json(url: str, body) -> dict:
        calls.append(("replay", url, body))
        if url.endswith("/dpps/issue"):
            return revision_1
        if url.endswith("/dpps/issuerA-pv-001/revise"):
            return revision_2
        raise AssertionError(f"Unexpected replay URL: {url}")

    monkeypatch.setattr(service, "_post_raw", post_raw)
    monkeypatch.setattr(service, "_post_json", post_json)

    imported = await service._import_revisions(_platform(), [revision_2, revision_1])

    assert imported == [revision_1, revision_2]
    assert calls == [
        ("admin-import", "http://dpp-platform-a:8080/admin/import-revisions", [revision_2, revision_1]),
        (
            "replay",
            "http://dpp-platform-a:8080/dpps/issue",
            {
                "dpp_id": "issuerA-pv-001",
                "schema_version": schema_version,
                "dpp_payload": {"foo": "one"},
            },
        ),
        (
            "replay",
            "http://dpp-platform-a:8080/dpps/issuerA-pv-001/revise",
            {
                "version": 2,
                "schema_version": schema_version,
                "dpp_payload": {"foo": "two"},
            },
        ),
    ]


@pytest.mark.asyncio
async def test_import_revisions_rejects_public_replay_for_different_issuer(monkeypatch):
    service = ScenarioService(None, None, None)
    revision = {
        "dpp_id": "issuerB-pv-001",
        "version": 1,
        "schema_version": {
            "subject_type": "pv_module",
            "major_version": 1,
            "minor_version": 0,
        },
        "dpp_payload": {"foo": "one"},
        "payload_hash": "hash-one",
    }

    async def post_raw(url: str, body) -> httpx.Response:
        return _response(404, url)

    monkeypatch.setattr(service, "_post_raw", post_raw)

    with pytest.raises(RuntimeError, match="public replay cannot preserve source DPP ID"):
        await service._import_revisions(_platform(), [revision])


@pytest.mark.asyncio
async def test_resolve_and_fetch_accepts_resolver_redirect(httpx_mock):
    service = ScenarioService(None, None, None)
    httpx_mock.add_response(
        method="GET",
        url="http://resolver:8080/s1_inverter/issuerB-s1-inv-001/1",
        status_code=302,
        headers={"Location": "http://dpp-platform-b:8080/dpps/issuerB-s1-inv-001/1"},
    )
    httpx_mock.add_response(
        method="GET",
        url="http://dpp-platform-a:8080/dpps/issuerB-s1-inv-001/1",
        status_code=200,
        json={"dpp_id": "issuerB-s1-inv-001", "version": 1},
    )

    resolved = await service._resolve_and_fetch(
        "http://resolver:8080",
        "s1_inverter",
        "issuerB-s1-inv-001",
        1,
        _platform(),
    )

    assert resolved == {
        "target_url": "http://dpp-platform-b:8080/dpps/issuerB-s1-inv-001/1",
        "data": {"dpp_id": "issuerB-s1-inv-001", "version": 1},
    }


@pytest.mark.asyncio
async def test_wait_for_revision_import_retries_transient_probe(monkeypatch):
    service = ScenarioService(None, None, None)
    calls = 0
    sleeps: list[float] = []

    async def probe(platform: PlatformRecord) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("platform still starting")
        return True

    async def sleep(delay_seconds: float) -> None:
        sleeps.append(delay_seconds)

    monkeypatch.setattr(service, "_platform_supports_revision_import", probe)
    monkeypatch.setattr("dpp_platform_factory.core.scenario_service.asyncio.sleep", sleep)

    supported = await service._wait_for_revision_import(_platform(), attempts=2, delay_seconds=0.25)

    assert supported is True
    assert calls == 2
    assert sleeps == [0.25]
