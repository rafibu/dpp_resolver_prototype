"""S4 predicate and reverse-traverse workload with mode equivalence checks."""

from __future__ import annotations

import copy
import httpx
import json
import os
import random
import structlog
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .results import WorkloadScenarioResult, WorkloadScenarioStep
from ..clients import (
    DppNotFoundError,
    DppSchemaVersion,
    IssueDppSpec,
    PlatformClient,
    ResolverClient,
    ReviseDppSpec,
)
from ..federation import FederationClient, PlatformInfo, PlatformStatus

logger = structlog.get_logger(__name__)

S4_SCENARIO_ID = "s4"
S4_DATASET_VERSION = 3
S4_REVISION_FRACTION = 0.20
S4_SCALE_TOTALS = {"small": 300, "medium": 5_000, "large": 25_000}


@dataclass(frozen=True)
class S4PlatformDefinition:
    """Stable logical ownership for one of the six S4 platform roles."""

    role: str
    issuer_id: str
    stack: str
    subject_types: tuple[str, ...]


S4_PLATFORM_DEFINITIONS = (
    S4PlatformDefinition(
        "component_supplier",
        "s4componentsupplier",
        "spring-postgres",
        ("component", "junction_box", "cable", "connector"),
    ),
    S4PlatformDefinition(
        "module_manufacturer",
        "s4modulemanufacturer",
        "fastapi-mongo",
        ("pv_module",),
    ),
    S4PlatformDefinition(
        "inverter_manufacturer",
        "s4invertermanufacturer",
        "spring-postgres",
        ("inverter",),
    ),
    S4PlatformDefinition(
        "battery_manufacturer",
        "s4batterymanufacturer",
        "fastapi-mongo",
        ("battery_pack",),
    ),
    S4PlatformDefinition(
        "installer_operator",
        "s4installeroperator",
        "spring-postgres",
        ("pv_installation",),
    ),
    S4PlatformDefinition(
        "recycler",
        "s4recycler",
        "fastapi-mongo",
        ("recycling_batch", "disposal_record"),
    ),
)

S4_SUBJECT_DISTRIBUTION = (
    ("component_supplier", "component", 0.09),
    ("component_supplier", "junction_box", 0.05),
    ("component_supplier", "cable", 0.05),
    ("component_supplier", "connector", 0.04),
    ("module_manufacturer", "pv_module", 0.30),
    ("inverter_manufacturer", "inverter", 0.12),
    ("battery_manufacturer", "battery_pack", 0.12),
    ("installer_operator", "pv_installation", 0.12),
    ("recycler", "recycling_batch", 0.08),
    ("recycler", "disposal_record", 0.03),
)

_ROLE_BY_SUBJECT_TYPE = {
    subject_type: definition.role
    for definition in S4_PLATFORM_DEFINITIONS
    for subject_type in definition.subject_types
}
_DEFINITION_BY_ROLE = {definition.role: definition for definition in S4_PLATFORM_DEFINITIONS}


@dataclass(frozen=True)
class S4GeneratedDpp:
    """One deterministic current DPP, with an optional revision-two payload."""

    role: str
    subject_type: str
    dpp_id: str
    payload: dict[str, Any]
    revision_payload: dict[str, Any] | None


@dataclass(frozen=True)
class S4Dataset:
    """The pure, repeatable dataset description used for S4 materialization."""

    seed: int
    scale: str
    dpps: tuple[S4GeneratedDpp, ...]

    @property
    def total_dpp_count(self) -> int:
        return len(self.dpps)

    @property
    def revision_count(self) -> int:
        return sum(dpp.revision_payload is not None for dpp in self.dpps)


@dataclass(frozen=True)
class S4Query:
    """A fixed platform-local benchmark query with AND-connected filters."""

    query_id: str
    result_mode: str
    subject_types: tuple[str, ...] = ()
    filters: tuple[dict[str, Any], ...] = ()
    return_fields: tuple[str, ...] = ()
    aggregate_path: str | None = None

    @property
    def subject_type(self) -> str:
        return ",".join(self.subject_types) if self.subject_types else "ALL"

    def request(self, execution_mode: str) -> dict[str, Any]:
        """Build the snake_case client request for one execution mode."""
        request: dict[str, Any] = {
            "result_mode": self.result_mode,
            "execution_mode": execution_mode,
            "filters": [copy.deepcopy(filter_) for filter_ in self.filters],
        }
        if self.subject_types:
            request["subject_types"] = list(self.subject_types)
        if self.return_fields:
            request["return_fields"] = list(self.return_fields)
        if self.aggregate_path is not None:
            request["aggregate_path"] = self.aggregate_path
        return request


@dataclass(frozen=True)
class S4TraverseQuery:
    """One fixed Java-compatible platform-local reverse-traverse query."""

    query_id: str
    subject_type: str
    dpp_id: str
    sources: tuple[dict[str, Any], ...]
    revision_number: int | None = None

    @property
    def source_subject_type(self) -> str:
        return str(self.sources[0]["subject_type"])

    def request(self, execution_mode: str) -> dict[str, Any]:
        request: dict[str, Any] = {
            "execution_mode": execution_mode,
            "subject_type": self.subject_type,
            "dpp_id": self.dpp_id,
            "sources": [copy.deepcopy(source) for source in self.sources],
        }
        if self.revision_number is not None:
            request["revision_number"] = self.revision_number
        return request


@dataclass(frozen=True)
class S4BenchmarkRecord:
    """One measured request made by S4 against a single platform."""

    scenario_name: str
    run_id: str
    seed: int
    scale: str
    platform_id: str
    subject_type: str
    query_id: str
    result_mode: str
    execution_mode: str
    request_payload: dict[str, Any]
    http_status: int | None
    duration_ms: float
    count: int | None
    aggregate: float | int | str | None
    match_count: int | None
    success: bool
    error_message: str | None
    response: dict[str, Any] | None
    query_category: str = "PREDICATE"
    equivalence: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready raw record without mutating the captured response."""
        return asdict(self)


@dataclass(frozen=True)
class S4Materialization:
    """Counts that distinguish fresh generation from deterministic re-use."""

    issued_dpps: int
    reused_dpps: int
    created_revisions: int


@dataclass(frozen=True)
class S4RunResult:
    """Outcome and artifacts of a completed S4 query evaluation."""

    success: bool
    run_id: str
    total_dpp_count: int
    generated_revisions: int
    records: tuple[S4BenchmarkRecord, ...]
    summary: dict[str, Any]
    raw_results_path: Path
    summary_path: Path


def resolve_s4_scale(scale: str) -> int:
    """Translate the documented S4 scale preset into an exact DPP count."""
    try:
        return S4_SCALE_TOTALS[scale.lower()]
    except KeyError as exc:
        valid = ", ".join(S4_SCALE_TOTALS)
        raise ValueError(f"Unknown S4 scale {scale!r}; choose one of: {valid}") from exc


def generate_s4_dataset(seed: int, scale: str = "medium") -> S4Dataset:
    """Create a deterministic, varied S4 dataset without contacting live services.

    Every generated DPP has an identity, technical, material, lifecycle, and
    traceability section. Query fields remain top-level scalars so both platform
    implementations can materialize them into their predicate-fact stores.
    """
    total = resolve_s4_scale(scale)
    normalized_scale = scale.lower()
    rng = random.Random(seed)
    records: list[S4GeneratedDpp] = []
    ordinal = 0

    for role, subject_type, count in _allocate_subject_counts(total):
        definition = _DEFINITION_BY_ROLE[role]
        for local_index in range(1, count + 1):
            ordinal += 1
            dpp_id = f"{definition.issuer_id}-s4-{subject_type}-{local_index:06d}"
            payload = _build_payload(
                role=role,
                subject_type=subject_type,
                ordinal=ordinal,
                dpp_id=dpp_id,
                seed=seed,
                scale=normalized_scale,
                rng=rng,
            )
            records.append(S4GeneratedDpp(role, subject_type, dpp_id, payload, None))

    records = _attach_s4_references(records)
    revision_total = max(1, round(total * S4_REVISION_FRACTION))
    revised_indices = set(rng.sample(range(len(records)), revision_total))
    # Guarantee at least one current-reference replacement at every scale
    # without changing the documented revision count.
    reference_changing_module_index = next(
        index
        for index, record in enumerate(records)
        if record.subject_type == "pv_module" and record.payload["components"]["primary_component"]["$ref"]
        != record.payload["workload_s4"]["reference_alternate_component"]
    )
    if reference_changing_module_index not in revised_indices:
        revised_indices.remove(min(revised_indices))
        revised_indices.add(reference_changing_module_index)
    revised_records: list[S4GeneratedDpp] = []
    for index, record in enumerate(records):
        revision_payload = _revise_payload(record.payload, record.subject_type,
                                           index) if index in revised_indices else None
        revised_records.append(
            S4GeneratedDpp(
                role=record.role,
                subject_type=record.subject_type,
                dpp_id=record.dpp_id,
                payload=record.payload,
                revision_payload=revision_payload,
            )
        )

    dataset = S4Dataset(seed=seed, scale=normalized_scale, dpps=tuple(revised_records))
    validate_s4_dataset_quality(dataset)
    return dataset


def _attach_s4_references(records: list[S4GeneratedDpp]) -> list[S4GeneratedDpp]:
    """Add deterministic, deliberately skewed current-state DPP references.

    The source graph stays platform-local for each benchmark request: modules
    point to components, installations to modules, and recycler records to
    disposed modules.  Hard references use revision 1, while battery packs
    carry a logical (soft) component reference for the logical-target query.
    """
    payload_by_id = {record.dpp_id: copy.deepcopy(record.payload) for record in records}
    ids_by_subject: dict[str, list[str]] = {}
    for record in records:
        ids_by_subject.setdefault(record.subject_type, []).append(record.dpp_id)

    component_ids = ids_by_subject["component"]
    junction_box_ids = ids_by_subject["junction_box"]
    cable_ids = ids_by_subject["cable"]
    connector_ids = ids_by_subject["connector"]
    module_ids = ids_by_subject["pv_module"]
    inverter_ids = ids_by_subject["inverter"]

    # These target choices create the query suite's high- and low-selectivity
    # cases.  They are stored as normal references, not special benchmark data.
    common_component = component_ids[0]
    rare_connector = connector_ids[-1]
    common_connector = connector_ids[0]

    for index, module_id in enumerate(module_ids):
        payload = payload_by_id[module_id]
        alternate_component = component_ids[1 + (index % (len(component_ids) - 1))]
        primary_component = (
            common_component if index % 5 else alternate_component
        )
        connector = rare_connector if index % 29 == 0 else common_connector
        payload["components"] = {
            "primary_component": {"$ref": f"component/{primary_component}/1"},
            "junction_box": {"$ref": f"junction_box/{junction_box_ids[index % len(junction_box_ids)]}/1"},
            "connector": {"$ref": f"connector/{connector}/1"},
            "cable": {"$ref": f"cable/{cable_ids[index % len(cable_ids)]}/1"},
        }
        payload["workload_s4"]["reference_alternate_component"] = f"component/{alternate_component}/1"

        # A deterministic subset is disposed and becomes the recycler target
        # set.  The pre-existing predicate fields remain meaningful.
        if index % 6 == 0:
            payload["disposal_status"] = "recycled"
            payload["operational_status"] = "recycled"
            payload.setdefault("disposal_date", f"2025-{index % 9 + 1:02d}-15")

    disposed_module_ids = [module_id for index, module_id in enumerate(module_ids) if index % 6 == 0]

    for index, battery_id in enumerate(ids_by_subject["battery_pack"]):
        payload_by_id[battery_id]["cell_component"] = {
            "$ref": f"component/{common_component if index % 4 else component_ids[-1]}"
        }

    for index, installation_id in enumerate(ids_by_subject["pv_installation"]):
        primary_module = module_ids[0] if index % 3 == 0 else module_ids[(index * 5) % len(module_ids)]
        payload = payload_by_id[installation_id]
        payload["primary_module"] = {"$ref": f"pv_module/{primary_module}/1"}
        payload["inverter"] = {"$ref": f"inverter/{inverter_ids[index % len(inverter_ids)]}/1"}

    for subject_type in ("recycling_batch", "disposal_record"):
        for index, record_id in enumerate(ids_by_subject[subject_type]):
            payload_by_id[record_id]["disposed_module"] = {
                "$ref": f"pv_module/{disposed_module_ids[index % len(disposed_module_ids)]}/1"
            }

    materialized: list[S4GeneratedDpp] = []
    for record in records:
        payload = payload_by_id[record.dpp_id]
        payload["workload_s4"]["source_dpp_id"] = record.dpp_id
        materialized.append(
            S4GeneratedDpp(record.role, record.subject_type, record.dpp_id, payload, None)
        )
    return materialized


def validate_s4_dataset_quality(dataset: S4Dataset) -> None:
    """Reject a too-small or uniform dataset before it becomes a misleading benchmark."""
    if dataset.total_dpp_count < 100:
        raise ValueError("S4 requires at least 100 DPPs to make predicate measurements meaningful")
    if dataset.revision_count == 0:
        raise ValueError("S4 requires revised DPPs to validate current-state predicate facts")

    modules = [dpp.payload for dpp in dataset.dpps if dpp.subject_type == "pv_module"]
    if not modules:
        raise ValueError("S4 requires PV modules for the fixed predicate query suite")
    lead_ratio = sum(module["contains_lead"] for module in modules) / len(modules)
    countries = {module["production_country"] for module in modules}
    missing_disposal_dates = sum("disposal_date" not in module for module in modules)
    if not 0.10 <= lead_ratio <= 0.45:
        raise ValueError(f"S4 lead distribution is not selective enough: {lead_ratio:.3f}")
    if len(countries) < 4 or missing_disposal_dates == 0:
        raise ValueError("S4 payload distribution lacks country or missing-value variation")

    current_modules = [dpp.revision_payload or dpp.payload for dpp in dataset.dpps if dpp.subject_type == "pv_module"]
    component_references = [
        module["components"]["primary_component"]["$ref"]
        for module in current_modules
    ]
    common_target = max(component_references.count(reference) for reference in set(component_references))
    connector_references = [module["components"]["connector"]["$ref"] for module in current_modules]
    rare_target = connector_references.count(connector_references[0])
    if common_target < 5 or len(set(component_references)) < 3 or rare_target == len(connector_references):
        raise ValueError("S4 traverse references lack a non-uniform incoming-reference distribution")
    if not any(
            dpp.revision_payload
            and dpp.payload.get("components", {}).get("primary_component")
            != dpp.revision_payload.get("components", {}).get("primary_component")
            for dpp in dataset.dpps
            if dpp.subject_type == "pv_module"
    ):
        raise ValueError("S4 requires a revised module to replace a current reference")


def build_s4_query_suite() -> tuple[S4Query, ...]:
    """Return the reviewer-facing cross-type predicate workload used by S4."""
    return (
        S4Query(
            "q1_factory_a_date_range_all_types",
            "SELECT",
            filters=(
                {"path": "manufacturing.facilityId", "operator": "EQ", "value": "factory-a"},
                {"path": "manufacturing.date", "operator": "GTE", "value": "2024-01-01"},
                {"path": "manufacturing.date", "operator": "LTE", "value": "2024-12-31"},
            ),
            return_fields=(
                "workload_s4.source_dpp_id",
                "serial_number",
                "manufacturing.facilityId",
                "manufacturing.date",
            ),
        ),
        S4Query(
            "q2_multi_factory_date_range_all_types",
            "SELECT",
            filters=(
                {"path": "manufacturing.facilityId", "operator": "IN", "value": ["factory-a", "factory-b", "factory-c"]},
                {"path": "manufacturing.date", "operator": "GTE", "value": "2024-03-01"},
                {"path": "manufacturing.date", "operator": "LTE", "value": "2024-09-30"},
            ),
            return_fields=(
                "workload_s4.source_dpp_id",
                "serial_number",
                "manufacturing.facilityId",
                "manufacturing.date",
            ),
        ),
        S4Query(
            "q3_store_17_suppliers_date_range",
            "SELECT",
            filters=(
                {"path": "logistics.destinationStoreId", "operator": "EQ", "value": "store-17"},
                {"path": "logistics.deliveryDate", "operator": "GTE", "value": "2024-01-01"},
                {"path": "logistics.deliveryDate", "operator": "LTE", "value": "2024-12-31"},
            ),
            return_fields=(
                "workload_s4.source_dpp_id",
                "manufacturing.facilityId",
                "logistics.destinationStoreId",
                "logistics.deliveryDate",
            ),
        ),
        S4Query(
            "q4_dpps_containing_lead",
            "SELECT",
            subject_types=("pv_module", "battery_pack"),
            filters=({"path": "materialComposition.materialId", "operator": "EQ", "value": "Pb"},),
            return_fields=(
                "workload_s4.source_dpp_id",
                "serial_number",
                "materialComposition.materialId",
                "materialComposition.mass",
                "materialComposition.unit",
            ),
        ),
        S4Query(
            "q5_total_lead_mass",
            "SUM",
            subject_types=("pv_module", "battery_pack"),
            filters=({"path": "materialComposition.materialId", "operator": "EQ", "value": "Pb"},),
            aggregate_path="materialComposition.mass",
        ),
    )


def build_s4_traverse_query_suite(dataset: S4Dataset) -> tuple[S4TraverseQuery, ...]:
    """Build the fixed, flattened reverse-traverse suite from S4 identities."""
    by_subject: dict[str, list[S4GeneratedDpp]] = {}
    for dpp in dataset.dpps:
        by_subject.setdefault(dpp.subject_type, []).append(dpp)

    common_component = by_subject["component"][0].dpp_id
    rare_connector = by_subject["connector"][-1].dpp_id
    selected_module = by_subject["pv_module"][0].dpp_id
    disposed_module = next(
        dpp.dpp_id
        for dpp in by_subject["pv_module"]
        if (dpp.revision_payload or dpp.payload).get("disposal_status") == "recycled"
    )

    return (
        S4TraverseQuery(
            "t1_common_component_revision",
            "component",
            common_component,
            ({"subject_type": "pv_module", "reference_paths": ["components.primary_component"]},),
            revision_number=1,
        ),
        S4TraverseQuery(
            "t2_rare_connector_revision",
            "connector",
            rare_connector,
            ({"subject_type": "pv_module", "reference_paths": ["components.connector"]},),
            revision_number=1,
        ),
        S4TraverseQuery(
            "t3_installations_using_module",
            "pv_module",
            selected_module,
            ({"subject_type": "pv_installation", "reference_paths": ["primary_module"]},),
            revision_number=1,
        ),
        S4TraverseQuery(
            "t4_recycling_batches_for_disposed_module",
            "pv_module",
            disposed_module,
            ({"subject_type": "recycling_batch", "reference_paths": ["disposed_module"]},),
            revision_number=1,
        ),
        S4TraverseQuery(
            "t5_logical_component_usage",
            "component",
            common_component,
            ({"subject_type": "battery_pack", "reference_paths": ["cell_component"]},),
        ),
    )


async def run_s4(
    factory_url: str,
    seed: int,
    output_dir: Path | None = None,
    scale: str = "medium",
    allow_mismatches: bool = False,
) -> S4RunResult:
    """Materialize S4 and compare indexed predicate and traverse queries.

    The scenario never resets or deletes federation resources. It owns only DPPs
    with deterministic ``s4-*`` issuer IDs and reuses them on re-runs with the
    same seed and scale. That keeps unrelated workload fixtures intact.
    """
    dataset = generate_s4_dataset(seed, scale)
    run_id = f"s4-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    async with FederationClient() as federation:
        resolver_url = await federation.get_resolver_url(factory_url)
        async with ResolverClient(resolver_url) as resolver:
            # The Factory registers a platform's declared subject types while
            # creating it.  Register schemas/types first so a fresh S4
            # federation can create all six roles successfully.
            schema_versions = await ensure_s4_schemas(resolver)
            platforms = await ensure_s4_platforms(federation, factory_url)
            await prepare_s4_platforms(resolver, platforms)
        materialization = await materialize_s4_dataset(dataset, platforms, schema_versions)

    records = annotate_s4_equivalence(await execute_s4_benchmark(dataset, platforms, run_id), dataset)
    summary = summarize_s4_benchmark(records, dataset, materialization)
    non_empty_checks = required_s4_non_empty_checks(records)
    summary["required_non_empty_checks"] = non_empty_checks
    summary["run_id"] = run_id
    success = all(record.success for record in records) and (
            allow_mismatches or all(query["equivalent"] for query in summary["queries"])
    )
    summary["success"] = success
    summary["allow_mismatches"] = allow_mismatches
    raw_results_path, summary_path = export_s4_results(output_dir, run_id, records, summary)
    logger.info(
        "s4_query_benchmark_complete",
        success=success,
        total_dpp_count=dataset.total_dpp_count,
        generated_revisions=dataset.revision_count,
        raw_results_path=str(raw_results_path),
        summary_path=str(summary_path),
    )
    return S4RunResult(
        success=success,
        run_id=run_id,
        total_dpp_count=dataset.total_dpp_count,
        generated_revisions=dataset.revision_count,
        records=tuple(records),
        summary=summary,
        raw_results_path=raw_results_path,
        summary_path=summary_path,
    )


async def run_s4_scenario(
        *,
        factory_url: str,
        resolver_url: str | None = None,
        seed: int = 42,
    output_dir: Path | None = None,
    scale: str = "medium",
    allow_mismatches: bool = False,
) -> WorkloadScenarioResult:
    """Run S4 through a reusable, structured scenario boundary.

    ``resolver_url`` is accepted for a uniform scenario API.  S4 deliberately
    discovers the resolver from the Factory so that its topology stays aligned
    with the CLI and the Factory-triggered execution paths.
    """
    del resolver_url
    try:
        result = await run_s4(factory_url, seed, output_dir, scale, allow_mismatches)
    except Exception as exc:
        error = _describe_exception(exc)
        logger.exception("s4_query_evaluation_failed", error=error)
        return WorkloadScenarioResult(
            scenario_id=S4_SCENARIO_ID,
            success=False,
            steps=(WorkloadScenarioStep("Run S4 query evaluation", "failed", error),),
            observations=(f"Failure: {error}",),
            report_md=_s4_failure_report(error),
        )

    report_md = build_s4_report(result)
    report_path = result.summary_path.with_suffix(".md")
    report_path.write_text(report_md, encoding="utf-8")
    return WorkloadScenarioResult(
        scenario_id=S4_SCENARIO_ID,
        success=result.success,
        steps=(
            WorkloadScenarioStep("Prepare deterministic S4 dataset", "passed"),
            WorkloadScenarioStep(
                "Compare INDEXED and ON_DEMAND query results",
                "passed" if result.success else "failed",
                None if result.success else "One or more query executions failed or produced non-equivalent results.",
            ),
            WorkloadScenarioStep("Write S4 benchmark artifacts", "passed"),
        ),
        observations=(
            f"Run ID: {result.run_id}",
            f"DPPs: {result.total_dpp_count}",
            f"Generated revisions: {result.generated_revisions}",
            f"Summary JSON: {result.summary_path}",
            f"Markdown report: {report_path}",
        ),
        report_md=report_md,
        summary=result.summary,
    )


def build_s4_report(result: S4RunResult) -> str:
    """Render the S4 summary in the Markdown shape used by scenario consumers."""
    summary = result.summary
    lines = [
        "# Scenario S4: Query Execution",
        "",
        f"- Status: `{'passed' if result.success else 'failed'}`",
        f"- Run ID: `{result.run_id}`",
        f"- Dataset: `{result.total_dpp_count}` DPPs; `{result.generated_revisions}` generated revisions",
        "",
        "## Query Equivalence",
    ]
    for query in summary.get("queries", []):
        status = "passed" if query.get("equivalent") else "failed"
        lines.append(
            f"- `{status}` {query.get('query_id', 'unknown')} "
            f"({query.get('query_category', 'PREDICATE')}, {query.get('result_mode', 'unknown')}): "
            f"INDEXED {query.get('duration_indexed_ms')} ms; "
            f"ON_DEMAND {query.get('duration_on_demand_ms')} ms"
        )
    lines.extend([
        "",
        "## Required Non-Empty Checks",
    ])
    for check in summary.get("required_non_empty_checks", []):
        status = "passed" if check.get("passed") else "failed"
        lines.append(
            f"- `{status}` {check.get('query_id', 'unknown')}: "
            f"INDEXED matches={check.get('indexed_match_count')}; "
            f"ON_DEMAND matches={check.get('on_demand_match_count')}"
        )
    lines.extend([
        "",
        "## Artifacts",
        f"- Raw results: `{result.raw_results_path}`",
        f"- Summary: `{result.summary_path}`",
    ])
    return "\n".join(lines)


def _s4_failure_report(error: str) -> str:
    return "\n".join([
        "# Scenario S4: Query Execution",
        "",
        "- Status: `failed`",
        "",
        "## Failure",
        f"- {error}",
    ])


def _describe_exception(exc: Exception) -> str:
    """Keep empty-message transport errors actionable in Factory/UI reports."""
    detail = str(exc).strip()
    if detail:
        return f"{type(exc).__name__}: {detail}"
    return f"{type(exc).__name__} (no detail provided)"


async def ensure_s4_platforms(
    federation: FederationClient,
    factory_url: str,
) -> dict[str, PlatformInfo]:
    """Find or create exactly the six S4 role platforms without altering others."""
    existing = {platform.issuer_id: platform for platform in await federation.list_platforms(factory_url)}
    platforms: dict[str, PlatformInfo] = {}

    for definition in S4_PLATFORM_DEFINITIONS:
        platform = existing.get(definition.issuer_id)
        if platform is None:
            platform = await federation.create_platform(
                factory_url,
                stack=definition.stack,
                issuer_id=definition.issuer_id,
                subject_types=list(definition.subject_types),
            )
            existing[definition.issuer_id] = platform
        else:
            missing_subjects = set(definition.subject_types) - set(platform.subject_types)
            if missing_subjects:
                raise RuntimeError(
                    f"S4 platform {platform.platform_id} ({definition.issuer_id}) is missing "
                    f"subject types: {', '.join(sorted(missing_subjects))}"
                )
            if platform.status == PlatformStatus.PAUSED:
                await federation.resume_platform(factory_url, platform.platform_id)
        platforms[definition.role] = platform

    return platforms
async def ensure_s4_schemas(resolver: ResolverClient) -> dict[str, DppSchemaVersion]:
    """Ensure payload-compatible active schemas for every S4 subject type."""
    versions: dict[str, DppSchemaVersion] = {}
    for subject_type in _ROLE_BY_SUBJECT_TYPE:
        await resolver.ensure_subject_type(subject_type)
        versions[subject_type] = await _ensure_s4_schema(resolver, subject_type)
    return versions


async def prepare_s4_platforms(
        resolver: ResolverClient,
        platforms: dict[str, PlatformInfo],
) -> None:
    """Register routes and cache S4 schemas on the role owning each subject type."""
    for definition in S4_PLATFORM_DEFINITIONS:
        platform = platforms[definition.role]
        async with PlatformClient(platform) as client:
            for subject_type in definition.subject_types:
                await resolver.ensure_platform_route(platform, subject_type)
                await client.ensure_subject_type(subject_type)
                await client.cache_schema(subject_type)


async def materialize_s4_dataset(
        dataset: S4Dataset,
        platforms: dict[str, PlatformInfo],
        schema_versions: dict[str, DppSchemaVersion],
) -> S4Materialization:
    """Issue missing S4 DPPs and complete only missing deterministic revisions."""
    issued = 0
    reused = 0
    revisions = 0
    by_role: dict[str, list[S4GeneratedDpp]] = {definition.role: [] for definition in S4_PLATFORM_DEFINITIONS}
    for dpp in dataset.dpps:
        by_role[dpp.role].append(dpp)

    for role, dpps in by_role.items():
        if not dpps:
            continue
        async with PlatformClient(platforms[role]) as client:
            for dpp in dpps:
                existing = await _get_existing_s4_dpp(client, dpp, dataset)
                if existing is None:
                    existing = await client.issue_dpp(
                        IssueDppSpec(
                            dpp_id=dpp.dpp_id,
                            schema_version=schema_versions[dpp.subject_type],
                            dpp_payload=dpp.payload,
                        )
                    )
                    issued += 1
                else:
                    reused += 1

                target_version = 2 if dpp.revision_payload is not None else 1
                if existing.version > target_version:
                    raise RuntimeError(
                        f"S4 DPP {dpp.dpp_id} has version {existing.version}, expected at most {target_version}; "
                        "refusing to overwrite an existing dataset."
                    )
                if dpp.revision_payload is not None and existing.version == 1:
                    await client.revise_dpp(
                        dpp.dpp_id,
                        ReviseDppSpec(
                            schema_version=schema_versions[dpp.subject_type],
                            dpp_payload=dpp.revision_payload,
                        ),
                    )
                    revisions += 1
    return S4Materialization(issued_dpps=issued, reused_dpps=reused, created_revisions=revisions)


async def execute_s4_benchmark(
        dataset: S4Dataset,
        platforms: dict[str, PlatformInfo],
        run_id: str,
) -> list[S4BenchmarkRecord]:
    """Run each fixed query in INDEXED and ON_DEMAND mode against its owner platform."""
    records: list[S4BenchmarkRecord] = []
    for query in build_s4_query_suite():
        for platform in _target_platforms_for_query(query, platforms):
            async with PlatformClient(platform) as client:
                for execution_mode in ("INDEXED", "ON_DEMAND"):
                    request = query.request(execution_mode)
                    started = time.perf_counter()
                    try:
                        execution = await client.query_predicate(request)
                        response = execution.response
                        records.append(
                            S4BenchmarkRecord(
                                scenario_name=S4_SCENARIO_ID,
                                run_id=run_id,
                                seed=dataset.seed,
                                scale=dataset.scale,
                                platform_id=platform.platform_id,
                                subject_type=query.subject_type,
                                query_id=query.query_id,
                                result_mode=query.result_mode,
                                query_category="PREDICATE",
                                execution_mode=execution_mode,
                                request_payload=request,
                                http_status=execution.status_code,
                                duration_ms=(time.perf_counter() - started) * 1000,
                                count=_response_count(response),
                                aggregate=response.get("aggregate"),
                                match_count=_response_match_count(response),
                                success=True,
                                error_message=None,
                                response=response,
                            )
                        )
                    except Exception as exc:
                        records.append(
                            S4BenchmarkRecord(
                                scenario_name=S4_SCENARIO_ID,
                                run_id=run_id,
                                seed=dataset.seed,
                                scale=dataset.scale,
                                platform_id=platform.platform_id,
                                subject_type=query.subject_type,
                                query_id=query.query_id,
                                result_mode=query.result_mode,
                                query_category="PREDICATE",
                                execution_mode=execution_mode,
                                request_payload=request,
                                http_status=_exception_http_status(exc),
                                duration_ms=(time.perf_counter() - started) * 1000,
                                count=None,
                                aggregate=None,
                                match_count=None,
                                success=False,
                                error_message=str(exc),
                                response=None,
                            )
                        )
    for query in build_s4_traverse_query_suite(dataset):
        role = _ROLE_BY_SUBJECT_TYPE[query.source_subject_type]
        platform = platforms[role]
        async with PlatformClient(platform) as client:
            for execution_mode in ("INDEXED", "ON_DEMAND"):
                request = query.request(execution_mode)
                started = time.perf_counter()
                try:
                    execution = await client.query_traverse(request)
                    response = execution.response
                    records.append(
                        S4BenchmarkRecord(
                            scenario_name=S4_SCENARIO_ID,
                            run_id=run_id,
                            seed=dataset.seed,
                            scale=dataset.scale,
                            platform_id=platform.platform_id,
                            subject_type=query.source_subject_type,
                            query_id=query.query_id,
                            result_mode="TRAVERSE",
                            query_category="TRAVERSE",
                            execution_mode=execution_mode,
                            request_payload=request,
                            http_status=execution.status_code,
                            duration_ms=(time.perf_counter() - started) * 1000,
                            count=_response_count(response),
                            aggregate=None,
                            match_count=_response_match_count(response),
                            success=True,
                            error_message=None,
                            response=response,
                        )
                    )
                except Exception as exc:
                    records.append(
                        S4BenchmarkRecord(
                            scenario_name=S4_SCENARIO_ID,
                            run_id=run_id,
                            seed=dataset.seed,
                            scale=dataset.scale,
                            platform_id=platform.platform_id,
                            subject_type=query.source_subject_type,
                            query_id=query.query_id,
                            result_mode="TRAVERSE",
                            query_category="TRAVERSE",
                            execution_mode=execution_mode,
                            request_payload=request,
                            http_status=_exception_http_status(exc),
                            duration_ms=(time.perf_counter() - started) * 1000,
                            count=None,
                            aggregate=None,
                            match_count=None,
                            success=False,
                            error_message=str(exc),
                            response=None,
                        )
                    )
    return records


def _target_platforms_for_query(query: S4Query, platforms: dict[str, PlatformInfo]) -> list[PlatformInfo]:
    if not query.subject_types:
        return [platforms[definition.role] for definition in S4_PLATFORM_DEFINITIONS]
    roles = {
        _ROLE_BY_SUBJECT_TYPE[subject_type]
        for subject_type in query.subject_types
    }
    return [platforms[definition.role] for definition in S4_PLATFORM_DEFINITIONS if definition.role in roles]


def summarize_s4_benchmark(
        records: list[S4BenchmarkRecord],
        dataset: S4Dataset,
        materialization: S4Materialization,
) -> dict[str, Any]:
    """Calculate per-query indexed/on-demand equivalence and performance summaries."""
    grouped: dict[tuple[str, str, str], dict[str, S4BenchmarkRecord]] = {}
    for record in records:
        grouped.setdefault((record.query_category, record.query_id, record.platform_id), {})[record.execution_mode] = record

    query_summaries: list[dict[str, Any]] = []
    for query in build_s4_query_suite():
        platform_ids = sorted(
            {
                record.platform_id
                for record in records
                if record.query_category == "PREDICATE" and record.query_id == query.query_id
            }
        )
        for platform_id in dict.fromkeys(platform_ids):
            modes = grouped.get(("PREDICATE", query.query_id, platform_id), {})
            indexed = modes.get("INDEXED")
            on_demand = modes.get("ON_DEMAND")
            equivalent = bool(
                indexed
                and on_demand
                and indexed.success
                and on_demand.success
                and predicate_results_equivalent(query.result_mode, indexed.response or {}, on_demand.response or {})
            )
            indexed_duration = indexed.duration_ms if indexed else None
            on_demand_duration = on_demand.duration_ms if on_demand else None
            speedup = (
                on_demand_duration / indexed_duration
                if indexed_duration is not None and on_demand_duration is not None and indexed_duration > 0
                else None
            )
            query_summaries.append(
                {
                    "query_id": query.query_id,
                    "query_category": "PREDICATE",
                    "platform_id": platform_id,
                    "subject_type": query.subject_type,
                    "subject_types": list(query.subject_types),
                    "result_mode": query.result_mode,
                    "duration_indexed_ms": indexed_duration,
                    "duration_on_demand_ms": on_demand_duration,
                    "speedup_factor": speedup,
                    "equivalent": equivalent,
                    "indexed_response": indexed.response if indexed else None,
                    "on_demand_response": on_demand.response if on_demand else None,
                }
            )

    for query in build_s4_traverse_query_suite(dataset):
        platform_id = next(
            (
                record.platform_id
                for record in records
                if record.query_category == "TRAVERSE" and record.query_id == query.query_id
            ),
            "",
        )
        modes = grouped.get(("TRAVERSE", query.query_id, platform_id), {})
        indexed = modes.get("INDEXED")
        on_demand = modes.get("ON_DEMAND")
        equivalent = bool(
            indexed
            and on_demand
            and indexed.success
            and on_demand.success
            and traverse_results_equivalent(indexed.response or {}, on_demand.response or {})
        )
        indexed_duration = indexed.duration_ms if indexed else None
        on_demand_duration = on_demand.duration_ms if on_demand else None
        speedup = (
            on_demand_duration / indexed_duration
            if indexed_duration is not None and on_demand_duration is not None and indexed_duration > 0
            else None
        )
        query_summaries.append(
            {
                "query_id": query.query_id,
                "query_category": "TRAVERSE",
                "platform_id": platform_id,
                "subject_type": query.subject_type,
                "source_subject_type": query.source_subject_type,
                "result_mode": "TRAVERSE",
                "duration_indexed_ms": indexed_duration,
                "duration_on_demand_ms": on_demand_duration,
                "speedup_factor": speedup,
                "equivalent": equivalent,
                "indexed_response": indexed.response if indexed else None,
                "on_demand_response": on_demand.response if on_demand else None,
            }
        )

    return {
        "scenario_name": S4_SCENARIO_ID,
        "seed": dataset.seed,
        "scale": dataset.scale,
        "total_dpp_count": dataset.total_dpp_count,
        "generated_revision_count": dataset.revision_count,
        "issued_dpp_count": materialization.issued_dpps,
        "reused_dpp_count": materialization.reused_dpps,
        "created_revision_count": materialization.created_revisions,
        "total_indexed_fact_count": None,
        "indexed_fact_count_available": False,
        "queries": query_summaries,
    }


def predicate_results_equivalent(
        result_mode: str,
        indexed: dict[str, Any],
        on_demand: dict[str, Any],
) -> bool:
    """Compare logical query results while ignoring ordering and transport metadata."""
    if result_mode == "SELECT":
        indexed_matches = indexed.get("matches") or []
        on_demand_matches = on_demand.get("matches") or []
        indexed_ids = _s4_source_ids(indexed_matches)
        on_demand_ids = _s4_source_ids(on_demand_matches)
        if indexed_ids is not None and on_demand_ids is not None:
            return indexed_ids == on_demand_ids
        return _canonical_match_set(indexed_matches) == _canonical_match_set(on_demand_matches)
    if result_mode == "COUNT":
        return indexed.get("count") == on_demand.get("count")
    if result_mode == "SUM":
        return _decimal_equal(indexed.get("aggregate"), on_demand.get("aggregate"))
    raise ValueError(f"Unsupported predicate result mode: {result_mode}")


def traverse_results_equivalent(indexed: dict[str, Any], on_demand: dict[str, Any]) -> bool:
    """Compare source-DPP identities despite Java's two response projections.

    Java returns flattened materialized-fact maps for INDEXED and full payloads
    for ON_DEMAND.  S4 embeds the stable source DPP ID in each generated
    payload, letting the benchmark compare the same logical match set without
    treating projection shape or ordering as a mismatch.
    """
    return _traverse_source_ids(indexed.get("matches")) == _traverse_source_ids(on_demand.get("matches"))


def annotate_s4_equivalence(
        records: list[S4BenchmarkRecord],
        dataset: S4Dataset,
) -> list[S4BenchmarkRecord]:
    """Write each query-pair's semantic equivalence back into its raw records."""
    by_key: dict[tuple[str, str, str], dict[str, S4BenchmarkRecord]] = {}
    for record in records:
        by_key.setdefault((record.query_category, record.query_id, record.platform_id), {})[record.execution_mode] = record

    equivalence: dict[tuple[str, str, str], bool] = {}
    for query in build_s4_query_suite():
        for key, modes in by_key.items():
            if key[0] != "PREDICATE" or key[1] != query.query_id:
                continue
            indexed, on_demand = modes.get("INDEXED"), modes.get("ON_DEMAND")
            equivalence[key] = bool(
                indexed and on_demand and indexed.success and on_demand.success
                and predicate_results_equivalent(query.result_mode, indexed.response or {}, on_demand.response or {})
            )
    for query in build_s4_traverse_query_suite(dataset):
        for key, modes in by_key.items():
            if key[0] != "TRAVERSE" or key[1] != query.query_id:
                continue
            indexed, on_demand = modes.get("INDEXED"), modes.get("ON_DEMAND")
            equivalence[key] = bool(
                indexed and on_demand and indexed.success and on_demand.success
                and traverse_results_equivalent(indexed.response or {}, on_demand.response or {})
            )
    return [replace(record, equivalence=equivalence.get((record.query_category, record.query_id, record.platform_id))) for record in
            records]


def required_s4_non_empty_checks(records: list[S4BenchmarkRecord]) -> list[dict[str, Any]]:
    """Require one deterministic predicate and one deterministic traverse query to be non-empty.

    S4 primarily checks INDEXED versus ON_DEMAND equivalence. These sentinel checks
    prevent a broken implementation from passing by returning empty results for
    both execution modes.
    """
    return [
        _required_s4_non_empty_check(
            records,
            query_category="PREDICATE",
            query_id="q4_dpps_containing_lead",
            description="Predicate sentinel: lead-containing DPPs must produce matches",
        ),
        _required_s4_non_empty_check(
            records,
            query_category="TRAVERSE",
            query_id="t1_common_component_revision",
            description="Traverse sentinel: common component reverse traversal must produce matches",
        ),
    ]


def _required_s4_non_empty_check(
        records: list[S4BenchmarkRecord],
        *,
        query_category: str,
        query_id: str,
        description: str,
) -> dict[str, Any]:
    matching_records = [
        record
        for record in records
        if record.query_category == query_category and record.query_id == query_id
    ]
    counts: dict[str, int | None] = {}
    for execution_mode in ("INDEXED", "ON_DEMAND"):
        mode_counts = [
            record.match_count
            for record in matching_records
            if record.execution_mode == execution_mode and record.match_count is not None
        ]
        counts[execution_mode] = sum(mode_counts) if mode_counts else None
    passed = (
            counts.get("INDEXED") is not None
            and counts.get("ON_DEMAND") is not None
            and counts["INDEXED"] > 0
            and counts["ON_DEMAND"] > 0
    )
    return {
        "query_category": query_category,
        "query_id": query_id,
        "description": description,
        "indexed_match_count": counts.get("INDEXED"),
        "on_demand_match_count": counts.get("ON_DEMAND"),
        "passed": passed,
    }


def export_s4_results(
        output_dir: Path | None,
        run_id: str,
        records: list[S4BenchmarkRecord],
        summary: dict[str, Any],
) -> tuple[Path, Path]:
    """Write raw executions and the derived comparison summary to normal output storage."""
    root = Path(output_dir) if output_dir is not None else Path(
        os.getenv("WORKLOAD_OUTPUT_DIR", "output")) / "predicate-queries"
    root.mkdir(parents=True, exist_ok=True)
    raw_path = root / f"{run_id}-predicate-results.json"
    summary_path = root / f"{run_id}-predicate-summary.json"
    raw_path.write_text(
        json.dumps(
            {
                "scenario_name": S4_SCENARIO_ID,
                "run_id": run_id,
                "records": [record.to_dict() for record in records],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return raw_path, summary_path


async def _ensure_s4_schema(resolver: ResolverClient, subject_type: str) -> DppSchemaVersion:
    """Use an existing permissive schema or publish an S4-compatible major version."""
    for major in range(1, 10):
        try:
            existing = await resolver.get_schema(subject_type, major, 0)
        except DppNotFoundError:
            await resolver.publish_schema(subject_type, major, 0, _s4_schema(subject_type))
            return DppSchemaVersion(subject_type=subject_type, major_version=major, minor_version=0)
        if _schema_accepts_s4_payload(subject_type, existing):
            return DppSchemaVersion(subject_type=subject_type, major_version=major, minor_version=0)
    raise RuntimeError(f"No S4-compatible schema major version available for {subject_type}")


async def _get_existing_s4_dpp(
        client: PlatformClient,
        generated: S4GeneratedDpp,
        dataset: S4Dataset,
) -> Any | None:
    try:
        existing = await client.get_revision(generated.dpp_id)
    except DppNotFoundError:
        return None

    metadata = existing.dpp_payload.get("workload_s4")
    if not isinstance(metadata, dict) or metadata.get("dataset_version") != S4_DATASET_VERSION:
        raise RuntimeError(
            f"DPP ID {generated.dpp_id} is already in use by data outside the S4 dataset; refusing to overwrite it."
        )
    if metadata.get("seed") != dataset.seed or metadata.get("scale") != dataset.scale:
        raise RuntimeError(
            f"Existing S4 DPP {generated.dpp_id} belongs to seed={metadata.get('seed')!r}, "
            f"scale={metadata.get('scale')!r}; requested seed={dataset.seed!r}, scale={dataset.scale!r}."
        )
    return existing


def _allocate_subject_counts(total: int) -> list[tuple[str, str, int]]:
    raw = [(role, subject_type, weight * total) for role, subject_type, weight in S4_SUBJECT_DISTRIBUTION]
    counts = [int(value) for _, _, value in raw]
    remaining = total - sum(counts)
    ranked = sorted(range(len(raw)), key=lambda index: raw[index][2] - counts[index], reverse=True)
    for index in ranked[:remaining]:
        counts[index] += 1
    return [(role, subject_type, counts[index]) for index, (role, subject_type, _) in enumerate(raw)]


def _build_payload(
        *,
        role: str,
        subject_type: str,
        ordinal: int,
        dpp_id: str,
        seed: int,
        scale: str,
        rng: random.Random,
) -> dict[str, Any]:
    serial = f"S4-{subject_type.upper().replace('_', '-')}-{ordinal:07d}"
    manufacturer = _weighted_choice(rng, (("HelioWorks", 0.38), ("NordCell", 0.24), ("TerraVolt", 0.21),
                                          ("Aster Energy", 0.17)))
    country = _weighted_choice(rng, (("CN", 0.46), ("DE", 0.17), ("US", 0.15), ("CH", 0.12), ("JP", 0.10)))
    payload: dict[str, Any] = {
        "serial_number": serial,
        "manufacturer": manufacturer,
        "model": f"{subject_type[:3].upper()}-{(ordinal % 37) + 1:03d}",
        "production_year": 2016 + (ordinal % 10),
        "production_country": country,
        "quality_score": round(72 + rng.random() * 27, 3),
        "identity": {
            "serial_number": serial,
            "manufacturer": {"name": manufacturer, "country": country, "facility": f"F-{ordinal % 19:02d}"},
            "batch": {"code": f"B-{seed}-{ordinal // 25:05d}", "line": f"L-{ordinal % 7 + 1}"},
        },
        "technical": {
            "rated_lifetime_years": 20 + ordinal % 11,
            "quality_score": round(72 + rng.random() * 27, 3),
            "certifications": ["IEC-61215", "ISO-14001", f"LOT-{ordinal % 9}"],
        },
        "material_composition": {
            "glass_mass_kg": round(8 + rng.random() * 18, 3),
            "aluminium_mass_kg": round(0.5 + rng.random() * 4, 3),
            "polymer_mass_kg": round(0.2 + rng.random() * 2, 3),
        },
        "lifecycle": {
            "status": "active",
            "inspection_history": [
                {"year": 2020 + ordinal % 5, "result": "passed"},
                {"year": 2025,
                 "result": _weighted_choice(rng, (("passed", 0.78), ("pending", 0.16), ("failed", 0.06)))},
            ],
        },
        "traceability": {
            "supplier_regions": [country, _weighted_choice(rng, (("EU", 0.42), ("APAC", 0.38), ("NA", 0.20)))],
            "quality_events": [{"kind": "audit", "score": round(80 + rng.random() * 19, 2)}],
        },
        "workload_s4": {
            "dataset_version": S4_DATASET_VERSION,
            "seed": seed,
            "scale": scale,
            "role": role,
            "logical_ordinal": ordinal,
            "target_revision": 1,
        },
    }

    if subject_type == "pv_module":
        contains_lead = rng.random() < 0.24
        recycled = rng.random() < 0.18
        payload.update(
            {
                "nominal_power_w": round(300 + rng.random() * 350, 2),
                "contains_lead": contains_lead,
                "lead_mass_kg": round(0.12 + rng.random() * 1.1, 4) if contains_lead else 0.0,
                "silver_mass_g": round(8 + rng.random() * 25, 3),
                "glass_mass_kg": round(9 + rng.random() * 16, 3),
                "frame_aluminium_mass_kg": round(0.8 + rng.random() * 3.5, 3),
                "hazardous_substance_flag": contains_lead and rng.random() < 0.45,
                "installation_country": _weighted_choice(rng, (("DE", 0.31), ("CH", 0.18), ("US", 0.22), ("ES", 0.29))),
                "operational_status": "recycled" if recycled else "active",
                "disposal_status": "recycled" if recycled else "active",
            }
        )
        if recycled:
            payload["disposal_date"] = f"202{ordinal % 5}-0{ordinal % 9 + 1}-15"
        payload["technical"].update({"nominal_power_w": payload["nominal_power_w"], "contains_lead": contains_lead})
    elif subject_type == "inverter":
        failures = 0 if rng.random() < 0.72 else rng.randint(1, 5)
        rated_power_kw = round(3 + rng.random() * 47, 2)
        payload.update(
            {
                "rated_power_kw": rated_power_kw,
                "max_ac_power_watts": round(rated_power_kw * 1_000, 2),
                "certification_status": _weighted_choice(rng,
                                                         (("certified", 0.82), ("pending", 0.12), ("expired", 0.06))),
                "repairable": rng.random() < 0.79,
                "failure_count": failures,
                "copper_mass_kg": round(0.7 + rng.random() * 7.5, 3),
                "firmware_version": f"{1 + ordinal % 4}.{ordinal % 10}.{ordinal % 13}",
            }
        )
        payload["technical"].update({"rated_power_kw": payload["rated_power_kw"], "failure_count": failures})
    elif subject_type == "battery_pack":
        chemistry = _weighted_choice(rng, (("LFP", 0.48), ("NMC", 0.36), ("NCA", 0.16)))
        cobalt = 0.0 if chemistry == "LFP" else round(0.35 + rng.random() * 2.8, 3)
        contains_lead = ordinal % 5 == 0
        payload.update(
            {
                "capacity_kwh": round(4 + rng.random() * 96, 3),
                "chemistry": chemistry,
                "lithium_mass_kg": round(0.8 + rng.random() * 12, 3),
                "cobalt_mass_kg": cobalt,
                "contains_lead": contains_lead,
                "lead_mass_kg": round(0.05 + rng.random() * 0.35, 4) if contains_lead else 0.0,
                "has_thermal_event_history": rng.random() < 0.055,
                "recycling_required": rng.random() < 0.34,
            }
        )
        payload["technical"].update({"capacity_kwh": payload["capacity_kwh"], "chemistry": chemistry})
    elif subject_type == "pv_installation":
        inspection_status = _weighted_choice(rng,
                                             (("passed", 0.63), ("pending", 0.19), ("overdue", 0.12), ("failed", 0.06)))
        payload.update(
            {
                "installation_id": f"INSTALL-{ordinal:07d}",
                "location_country": _weighted_choice(rng, (("DE", 0.28), ("CH", 0.18), ("US", 0.23), ("ES", 0.31))),
                "location_region": f"R-{ordinal % 23:02d}",
                "commissioning_year": 2014 + ordinal % 12,
                "total_power_kw": round(5 + rng.random() * 950, 2),
                "module_count": 12 + ordinal % 780,
                "grid_connected": rng.random() < 0.91,
                "inspection_status": inspection_status,
                "has_fire_incident": rng.random() < 0.035,
            }
        )
        payload["lifecycle"].update({"inspection_status": inspection_status})
    elif subject_type in {"recycling_batch", "disposal_record"}:
        toxic = rng.random() < 0.065
        payload.update(
            {
                "disposal_method": _weighted_choice(rng, (("mechanical_recycling", 0.56), ("thermal_recovery", 0.24),
                                                          ("controlled_landfill", 0.20))),
                "disposal_year": 2020 + ordinal % 7,
                "recovered_glass_kg": round(10 + rng.random() * 850, 3),
                "recovered_aluminium_kg": round(1 + rng.random() * 140, 3),
                "recovered_silver_g": round(rng.random() * 850, 3),
                "landfill_fraction_pct": round(rng.random() * 35, 3),
                "toxic_leak_reported": toxic,
            }
        )
        payload["lifecycle"].update({"disposal_method": payload["disposal_method"], "toxic_leak_reported": toxic})
    else:
        payload.update(
            {
                "component_category": subject_type,
                "recycled_content_pct": round(rng.random() * 82, 3),
                "hazardous_substance_flag": rng.random() < 0.08,
            }
        )
    _add_common_projected_facts(payload, subject_type, ordinal)
    return payload


def _add_common_projected_facts(payload: dict[str, Any], subject_type: str, ordinal: int) -> None:
    """Add S4 reviewer-use-case projected facts shared across subject types."""
    facility_id = ("factory-a", "factory-b", "factory-c", "factory-d")[ordinal % 4]
    manufacturing_date = f"2024-{(ordinal % 12) + 1:02d}-{(ordinal % 28) + 1:02d}"
    destination_store = "store-17" if ordinal % 3 == 0 else f"store-{10 + (ordinal % 9)}"
    delivery_date = f"2024-{((ordinal + 2) % 12) + 1:02d}-{((ordinal + 5) % 28) + 1:02d}"

    payload["manufacturing"] = {
        "facilityId": facility_id,
        "date": manufacturing_date,
    }
    payload["logistics"] = {
        "destinationStoreId": destination_store,
        "deliveryDate": delivery_date,
    }
    payload["lifecycle"].update(
        {
            "disposalMethod": payload.get("disposal_method", payload.get("disposal_status", "none")),
            "disposalDate": payload.get("disposal_date", ""),
        }
    )
    _sync_material_projection(payload, subject_type)


def _sync_material_projection(payload: dict[str, Any], subject_type: str) -> None:
    contains_lead = bool(payload.get("contains_lead"))
    lead_mass = float(payload.get("lead_mass_kg") or 0.0)
    if contains_lead and lead_mass > 0:
        material_id = "Pb"
        mass = round(lead_mass, 4)
    elif subject_type == "inverter":
        material_id = "Cu"
        mass = round(float(payload.get("copper_mass_kg") or 0.0), 4)
    elif subject_type == "battery_pack":
        material_id = "Li"
        mass = round(float(payload.get("lithium_mass_kg") or 0.0), 4)
    else:
        material_id = "Al"
        mass = round(float(payload.get("frame_aluminium_mass_kg") or payload.get("recovered_aluminium_kg") or 0.0), 4)
    payload["materialComposition"] = {
        "materialId": material_id,
        "mass": mass,
        "unit": "kg",
    }


def _revise_payload(payload: dict[str, Any], subject_type: str, index: int) -> dict[str, Any]:
    """Create revision two with predicate and, where relevant, reference changes."""
    revised = copy.deepcopy(payload)
    revised["workload_s4"]["target_revision"] = 2
    revised["workload_s4"]["revision_reason"] = "s4_current_state_predicate_update"
    if subject_type == "pv_module":
        alternate_reference = revised["workload_s4"].get("reference_alternate_component")
        if alternate_reference:
            revised["components"]["primary_component"] = {"$ref": alternate_reference}
            revised["workload_s4"]["reference_revision_changed"] = True
        if not revised["contains_lead"]:
            revised["contains_lead"] = True
            revised["lead_mass_kg"] = 0.35 + (index % 7) * 0.08
            revised["hazardous_substance_flag"] = True
        elif revised["disposal_status"] == "active":
            revised["disposal_status"] = "recycled"
            revised["operational_status"] = "recycled"
            revised["disposal_date"] = f"2026-0{index % 9 + 1}-20"
        else:
            revised["nominal_power_w"] = round(revised["nominal_power_w"] + 7.5, 2)
        revised["technical"]["contains_lead"] = revised["contains_lead"]
        revised["technical"]["nominal_power_w"] = revised["nominal_power_w"]
    elif subject_type == "inverter":
        revised["failure_count"] += 1
        revised["firmware_version"] = f"2.{index % 10}.{index % 17}"
        revised["technical"]["failure_count"] = revised["failure_count"]
    elif subject_type == "battery_pack":
        revised["recycling_required"] = True
        revised["cobalt_mass_kg"] = round(revised["cobalt_mass_kg"] + 0.15, 3)
        revised["technical"]["capacity_kwh"] = round(revised["capacity_kwh"] * 0.98, 3)
    elif subject_type == "pv_installation":
        revised["inspection_status"] = "passed"
        revised["has_fire_incident"] = False
        revised["lifecycle"]["inspection_status"] = "passed"
    elif subject_type in {"recycling_batch", "disposal_record"}:
        revised["recovered_aluminium_kg"] = round(revised["recovered_aluminium_kg"] * 1.04, 3)
        revised["landfill_fraction_pct"] = round(max(0, revised["landfill_fraction_pct"] - 1.0), 3)
    else:
        revised["quality_score"] = round(min(100, revised["quality_score"] + 1.5), 3)
        revised["technical"]["quality_score"] = revised["quality_score"]
    _sync_material_projection(revised, subject_type)
    return revised


def _s4_schema(subject_type: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://dpp.example.org/schemas/{subject_type}/s4",
        "title": f"S4 Predicate Query {subject_type}",
        "type": "object",
        "properties": {
            "serial_number": {"type": "string"},
            "manufacturer": {"type": "string"},
            "workload_s4": {"type": "object"},
        },
        "required": ["serial_number", "manufacturer", "workload_s4"],
        "additionalProperties": True,
    }


def _schema_accepts_s4_payload(subject_type: str, schema: dict[str, Any]) -> bool:
    if schema.get("type") != "object" or schema.get("additionalProperties") is False:
        return False
    required = set(schema.get("required") or [])
    return required.issubset(_s4_payload_keys(subject_type))


def _s4_payload_keys(subject_type: str) -> set[str]:
    common = {
        "serial_number", "manufacturer", "model", "production_year",
        "production_country", "workload_s4", "manufacturing", "logistics",
        "materialComposition",
    }
    specific = {
        "pv_module": {"nominal_power_w", "contains_lead", "lead_mass_kg"},
        "inverter": {"rated_power_kw", "max_ac_power_watts", "failure_count"},
        "battery_pack": {"capacity_kwh", "chemistry", "cobalt_mass_kg"},
        "pv_installation": {"installation_id", "inspection_status", "has_fire_incident"},
        "recycling_batch": {"recovered_aluminium_kg", "toxic_leak_reported"},
        "disposal_record": {"recovered_aluminium_kg", "toxic_leak_reported"},
    }
    return common | specific.get(subject_type, {"component_category", "recycled_content_pct"})


def _weighted_choice(rng: random.Random, choices: tuple[tuple[Any, float], ...]) -> Any:
    threshold = rng.random() * sum(weight for _, weight in choices)
    cumulative = 0.0
    for value, weight in choices:
        cumulative += weight
        if threshold <= cumulative:
            return value
    return choices[-1][0]


def _canonical_match_set(matches: Any) -> tuple[str, ...]:
    values = matches if isinstance(matches, list) else [matches]
    return tuple(sorted(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str) for value in values))


def _s4_source_ids(matches: Any) -> tuple[str, ...] | None:
    values = matches if isinstance(matches, list) else []
    identities: list[str] = []
    for match in values:
        source_id = _s4_source_id(match)
        if source_id is None:
            return None
        identities.append(str(source_id))
    return tuple(sorted(identities))


def _s4_source_id(match: Any) -> Any | None:
    if not isinstance(match, dict):
        return None
    metadata = match.get("workload_s4")
    if isinstance(metadata, dict) and metadata.get("source_dpp_id") is not None:
        return metadata["source_dpp_id"]
    return match.get("workload_s4.source_dpp_id")


def _traverse_source_ids(matches: Any) -> tuple[str, ...]:
    values = matches if isinstance(matches, list) else []
    identities: list[str] = []
    for match in values:
        if not isinstance(match, dict):
            identities.append(json.dumps(match, sort_keys=True, default=str))
            continue
        source_id = _s4_source_id(match)
        # The fallback retains useful mismatch diagnostics for a non-S4 or
        # malformed response instead of falsely treating all such matches equal.
        identities.append(str(source_id) if source_id is not None else json.dumps(match, sort_keys=True, default=str))
    return tuple(sorted(identities))


def _decimal_equal(left: Any, right: Any) -> bool:
    try:
        return abs(Decimal(str(left)) - Decimal(str(right))) <= Decimal("0.000001")
    except (InvalidOperation, ValueError):
        return False


def _response_count(response: dict[str, Any]) -> int | None:
    value = response.get("count")
    return value if isinstance(value, int) else None


def _response_match_count(response: dict[str, Any]) -> int | None:
    matches = response.get("matches")
    if isinstance(matches, list):
        return len(matches)
    count = response.get("count")
    return count if isinstance(count, int) else None


def _exception_http_status(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None
