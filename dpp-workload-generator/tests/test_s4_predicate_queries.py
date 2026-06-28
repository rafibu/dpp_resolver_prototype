import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from workload.clients import PredicateQueryExecution, TraverseQueryExecution
from workload.federation import PlatformInfo, PlatformStatus
from workload.scenarios import s4


def _platform(definition: s4.S4PlatformDefinition, index: int = 1) -> PlatformInfo:
    return PlatformInfo(
        platform_id=f"platform-s4-{index}",
        stack=definition.stack,
        issuer_id=definition.issuer_id,
        subject_types=list(definition.subject_types),
        external_url=f"http://platform-s4-{index}:8080",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(timezone.utc),
    )


def _platforms() -> dict[str, PlatformInfo]:
    return {
        definition.role: _platform(definition, index)
        for index, definition in enumerate(s4.S4_PLATFORM_DEFINITIONS, start=1)
    }


def _has_path(payload: dict, path: str) -> bool:
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def test_dataset_generation_is_deterministic_and_non_uniform():
    first = s4.generate_s4_dataset(seed=41, scale="small")
    second = s4.generate_s4_dataset(seed=41, scale="small")

    assert first == second
    assert first.total_dpp_count == 300
    assert first.revision_count == 60
    assert len({dpp.payload["production_country"] for dpp in first.dpps}) >= 4
    assert len({dpp.payload["manufacturer"] for dpp in first.dpps}) > 1
    assert len({str(dpp.payload) for dpp in first.dpps}) == first.total_dpp_count


def test_generated_payloads_are_nested_and_cover_query_fields():
    dataset = s4.generate_s4_dataset(seed=7, scale="small")
    module = next(dpp for dpp in dataset.dpps if dpp.subject_type == "pv_module")

    assert {"identity", "technical", "material_composition", "lifecycle", "traceability"}.issubset(module.payload)
    assert {"manufacturing", "logistics", "materialComposition", "contains_lead", "lead_mass_kg"}.issubset(module.payload)
    assert module.payload["materialComposition"]["unit"] == "kg"
    assert any("disposal_date" not in dpp.payload for dpp in dataset.dpps if dpp.subject_type == "pv_module")

    subject_payloads = {
        subject_type: next(dpp.payload for dpp in dataset.dpps if dpp.subject_type == subject_type)
        for query in s4.build_s4_query_suite()
        for subject_type in (query.subject_types or ("pv_module",))
    }
    for query in s4.build_s4_query_suite():
        payload = subject_payloads[(query.subject_types or ("pv_module",))[0]]
        for filter_ in query.filters:
            if filter_["operator"] != "NOT_EXISTS":
                assert _has_path(payload, filter_["path"])
        for field in query.return_fields:
            assert _has_path(payload, field)
        if query.aggregate_path:
            assert _has_path(payload, query.aggregate_path)


def test_revisions_change_projected_current_state_values():
    dataset = s4.generate_s4_dataset(seed=13, scale="small")
    revised = [dpp for dpp in dataset.dpps if dpp.revision_payload is not None]

    assert revised
    assert all(dpp.payload != dpp.revision_payload for dpp in revised)
    assert any(
        dpp.payload.get("contains_lead") != dpp.revision_payload.get("contains_lead")
        or dpp.payload.get("failure_count") != dpp.revision_payload.get("failure_count")
        or dpp.payload.get("inspection_status") != dpp.revision_payload.get("inspection_status")
        or dpp.payload.get("recovered_aluminium_kg") != dpp.revision_payload.get("recovered_aluminium_kg")
        for dpp in revised
    )


def test_query_suite_builds_indexed_and_on_demand_requests():
    query = next(query for query in s4.build_s4_query_suite() if query.query_id == "q2_multi_factory_date_range_all_types")

    indexed = query.request("INDEXED")
    on_demand = query.request("ON_DEMAND")

    assert indexed["execution_mode"] == "INDEXED"
    assert on_demand["execution_mode"] == "ON_DEMAND"
    assert indexed["filters"][0]["value"] == ["factory-a", "factory-b", "factory-c"]
    assert "subject_types" not in indexed

    lead = next(query for query in s4.build_s4_query_suite() if query.query_id == "q4_dpps_containing_lead")
    assert lead.request("INDEXED")["subject_types"] == ["pv_module", "battery_pack"]


def test_traverse_dataset_is_deterministic_skewed_and_revised():
    dataset = s4.generate_s4_dataset(seed=31, scale="small")
    modules = [dpp.revision_payload or dpp.payload for dpp in dataset.dpps if dpp.subject_type == "pv_module"]
    incoming = {}
    for module in modules:
        ref = module["components"]["primary_component"]["$ref"]
        incoming[ref] = incoming.get(ref, 0) + 1

    assert max(incoming.values()) > 10
    assert any(count == 1 for count in incoming.values())
    assert any(
        dpp.revision_payload
        and dpp.payload["components"]["primary_component"]
        != dpp.revision_payload["components"]["primary_component"]
        for dpp in dataset.dpps
        if dpp.subject_type == "pv_module"
    )


def test_traverse_query_suite_builds_flattened_mode_requests_and_equivalence():
    dataset = s4.generate_s4_dataset(seed=17, scale="small")
    query = s4.build_s4_traverse_query_suite(dataset)[0]

    indexed = query.request("INDEXED")
    on_demand = query.request("ON_DEMAND")

    assert indexed["execution_mode"] == "INDEXED"
    assert on_demand["execution_mode"] == "ON_DEMAND"
    assert "target" not in indexed
    assert indexed["sources"][0]["reference_paths"] == ["components.primary_component"]
    assert s4.traverse_results_equivalent(
        {"matches": [{"workload_s4.source_dpp_id": "module-1"}]},
        {"matches": [{"workload_s4": {"source_dpp_id": "module-1"}}]},
    )


@pytest.mark.parametrize(
    ("result_mode", "indexed", "on_demand"),
    [
        ("SELECT", {"matches": [{"serial_number": "A"}, {"serial_number": "B"}]}, {"matches": [{"serial_number": "B"}, {"serial_number": "A"}]}),
        ("COUNT", {"count": 7}, {"count": 7}),
        ("SUM", {"aggregate": 12.5}, {"aggregate": "12.5000001"}),
    ],
)
def test_predicate_equivalence_handles_select_count_and_sum(result_mode, indexed, on_demand):
    assert s4.predicate_results_equivalent(result_mode, indexed, on_demand)


def test_predicate_equivalence_detects_mismatch():
    assert not s4.predicate_results_equivalent("COUNT", {"count": 2}, {"count": 3})
    assert not s4.predicate_results_equivalent("SELECT", {"matches": [{"serial_number": "A"}]}, {"matches": []})


def test_summary_calculates_speedup_and_mismatch():
    dataset = s4.generate_s4_dataset(seed=5, scale="small")
    records = [
        s4.S4BenchmarkRecord(
            scenario_name="s4",
            run_id="run",
            seed=5,
            scale="small",
            platform_id="platform-s4-2",
            subject_type="pv_module,battery_pack",
            query_id="q4_dpps_containing_lead",
            result_mode="SELECT",
            execution_mode="INDEXED",
            request_payload={},
            http_status=200,
            duration_ms=5.0,
            count=None,
            aggregate=None,
            match_count=1,
            success=True,
            error_message=None,
            response={"matches": [{"serial_number": "A"}]},
        ),
        s4.S4BenchmarkRecord(
            scenario_name="s4",
            run_id="run",
            seed=5,
            scale="small",
            platform_id="platform-s4-2",
            subject_type="pv_module,battery_pack",
            query_id="q4_dpps_containing_lead",
            result_mode="SELECT",
            execution_mode="ON_DEMAND",
            request_payload={},
            http_status=200,
            duration_ms=15.0,
            count=None,
            aggregate=None,
            match_count=1,
            success=True,
            error_message=None,
            response={"matches": [{"serial_number": "B"}]},
        ),
    ]

    summary = s4.summarize_s4_benchmark(records, dataset, s4.S4Materialization(1, 0, 0))
    q1 = next(query for query in summary["queries"] if query["query_id"] == "q4_dpps_containing_lead")

    assert q1["speedup_factor"] == 3.0
    assert q1["equivalent"] is False
    assert summary["total_dpp_count"] == 300


def test_result_export_writes_raw_and_summary_files(tmp_path):
    record = s4.S4BenchmarkRecord(
        scenario_name="s4",
        run_id="s4-test",
        seed=42,
        scale="small",
        platform_id="platform-s4-2",
        subject_type="pv_module",
        query_id="q1",
        result_mode="COUNT",
        execution_mode="INDEXED",
        request_payload={"result_mode": "COUNT"},
        http_status=200,
        duration_ms=1.5,
        count=4,
        aggregate=None,
        match_count=4,
        success=True,
        error_message=None,
        response={"count": 4},
    )

    raw_path, summary_path = s4.export_s4_results(tmp_path, "s4-test", [record], {"success": True})

    assert raw_path.exists()
    assert summary_path.exists()
    assert '"query_id": "q1"' in raw_path.read_text(encoding="utf-8")
    assert '"success": true' in summary_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_ensure_s4_platforms_creates_missing_roles_without_touching_existing():
    class FakeFederation:
        def __init__(self):
            self.created: list[tuple[str, str, list[str]]] = []

        async def list_platforms(self, factory_url: str):
            return [_platform(s4.S4_PLATFORM_DEFINITIONS[0])]

        async def create_platform(self, factory_url: str, *, stack: str, issuer_id: str, subject_types: list[str]):
            self.created.append((stack, issuer_id, subject_types))
            definition = next(item for item in s4.S4_PLATFORM_DEFINITIONS if item.issuer_id == issuer_id)
            return _platform(definition, len(self.created) + 1)

        async def resume_platform(self, factory_url: str, platform_id: str):
            raise AssertionError("A running platform must not be resumed")

    federation = FakeFederation()
    platforms = await s4.ensure_s4_platforms(federation, "http://factory")

    assert len(platforms) == 6
    assert len(federation.created) == 5
    assert all(issuer_id.startswith("s4") for _, issuer_id, _ in federation.created)


@pytest.mark.asyncio
async def test_ensure_s4_platforms_reuses_all_existing_roles_without_duplicates():
    class FakeFederation:
        async def list_platforms(self, factory_url: str):
            return [_platform(definition, index) for index, definition in enumerate(s4.S4_PLATFORM_DEFINITIONS, start=1)]

        async def create_platform(self, *args, **kwargs):
            raise AssertionError("Existing S4 platforms must be reused")

        async def resume_platform(self, *args, **kwargs):
            raise AssertionError("No platform is paused")

    platforms = await s4.ensure_s4_platforms(FakeFederation(), "http://factory")

    assert set(platforms) == {definition.role for definition in s4.S4_PLATFORM_DEFINITIONS}


@pytest.mark.asyncio
async def test_existing_s4_dataset_is_reused_and_seed_conflicts_are_rejected():
    dataset = s4.generate_s4_dataset(seed=19, scale="small")
    generated = dataset.dpps[0]

    class FakeClient:
        def __init__(self, payload):
            self.payload = payload

        async def get_revision(self, dpp_id: str):
            return SimpleNamespace(dpp_payload=self.payload, version=1)

    reused = await s4._get_existing_s4_dpp(FakeClient(generated.payload), generated, dataset)
    assert reused.version == 1

    conflicting = dict(generated.payload)
    conflicting["workload_s4"] = dict(conflicting["workload_s4"], seed=99)
    with pytest.raises(RuntimeError, match="belongs to seed"):
        await s4._get_existing_s4_dpp(FakeClient(conflicting), generated, dataset)


@pytest.mark.asyncio
async def test_benchmark_records_indexed_and_on_demand_and_detects_mismatch(monkeypatch):
    class FakeClient:
        def __init__(self, platform: PlatformInfo):
            self.platform = platform

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def query_predicate(self, request: dict):
            mode = request["execution_mode"]
            if request["result_mode"] == "SELECT":
                response = {"matches": [{"serial_number": "S4-ONE"}]}
            elif request["result_mode"] == "COUNT":
                response = {"count": 3}
            else:
                response = {"aggregate": 12.75}
            if request.get("subject_types") == ["pv_module", "battery_pack"] and mode == "ON_DEMAND":
                response = {"count": 4}
            return PredicateQueryExecution(response=response, status_code=200)

        async def query_traverse(self, request: dict):
            source = request["sources"][0]["subject_type"]
            response = {
                "platform_id": "fake",
                "subject_type": request["subject_type"],
                "dpp_id": request["dpp_id"],
                "matches": [{
                    "workload_s4": {"source_dpp_id": f"{source}-source"},
                }],
            }
            return TraverseQueryExecution(response=response, status_code=200)

    monkeypatch.setattr(s4, "PlatformClient", FakeClient)
    dataset = s4.generate_s4_dataset(seed=23, scale="small")
    records = await s4.execute_s4_benchmark(dataset, _platforms(), "run")
    summary = s4.summarize_s4_benchmark(records, dataset, s4.S4Materialization(300, 0, 60))

    expected_predicate_pairs = sum(
        len(s4._target_platforms_for_query(query, _platforms()))
        for query in s4.build_s4_query_suite()
    )
    assert len(records) == (
        expected_predicate_pairs + len(s4.build_s4_traverse_query_suite(dataset))
    ) * 2
    assert {record.execution_mode for record in records} == {"INDEXED", "ON_DEMAND"}
    assert {record.query_category for record in records} == {"PREDICATE", "TRAVERSE"}
    mismatches = [query for query in summary["queries"] if query["query_id"] == "q5_total_lead_mass"]
    assert mismatches
    assert any(query["equivalent"] is False for query in mismatches)
