import asyncio
import copy
import httpx
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from .platform_service import PlatformService
from .schema_seed_service import SchemaSeedService
from .state import FactoryState, PlatformRecord, PlatformStatus
from ..api.api_models import ScenarioStatus, ScenarioStep

SCENARIO_IDS = ("s1", "s2", "s3", "s4", "s5")

S1_INVERTER_TYPE = "s1_inverter"
S1_INSTALLATION_TYPE = "s1_pv_installation"


class S4WorkloadFailure(RuntimeError):
    """Preserves the workload Markdown report when S4 finishes unsuccessfully."""

    def __init__(self, report_md: str | None, message: str) -> None:
        super().__init__(message)
        self.report_md = report_md


class ScenarioService:
    def __init__(
        self,
        state: FactoryState,
        platform_service: PlatformService,
        schema_seed_service: SchemaSeedService,
    ) -> None:
        self.state = state
        self.platform_service = platform_service
        self.schema_seed_service = schema_seed_service

    async def run(self, scenario_id: str) -> ScenarioStatus:
        steps: list[ScenarioStep] = []
        observations: list[str] = []
        started = time.perf_counter()
        workload_report: str | None = None

        async def checked(name: str, action: Callable[[], Awaitable[Any]]) -> Any:
            step = ScenarioStep(name=name, status="running")
            steps.append(step)
            try:
                result = await action()
                step.status = "passed"
                return result
            except Exception as exc:
                step.status = "failed"
                step.error = str(exc)
                raise

        try:
            if scenario_id == "s1":
                await self._run_s1(checked, observations)
            elif scenario_id == "s2":
                await self._run_s2(checked, observations)
            elif scenario_id == "s3":
                await self._run_s3(checked, observations)
            elif scenario_id == "s4":
                workload_report = await self._run_s4(checked, observations)
            elif scenario_id == "s5":
                await self._run_s5(checked, observations)
            else:
                raise ValueError(f"Unknown scenario: {scenario_id}")
            status = "passed"
        except S4WorkloadFailure as exc:
            status = "failed"
            workload_report = exc.report_md
            observations.append(f"Failure: {exc}")
        except Exception as exc:
            status = "failed"
            observations.append(f"Failure: {exc}")

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        report = workload_report or _build_report(scenario_id, status, elapsed_ms, steps, observations)
        return ScenarioStatus(
            scenario_id=scenario_id,
            status=status,
            steps=steps,
            report_md=report,
        )

    async def _run_s1(
        self,
        checked: Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]],
        observations: list[str],
    ) -> None:
        resolver, platforms = await checked("Discover resolver and default platforms", self._require_federation)
        resolver_url = _resolver_url(resolver)
        platform_a = _find_platform(platforms, "pv_module")
        platform_b = _find_platform(platforms, "inverter")
        successor_platform: PlatformRecord | None = None
        inverter_revision_1: dict | None = None
        inverter_revision_2: dict | None = None
        installation_revision: dict | None = None
        hard_target_before = ""

        try:
            await checked("Ensure source platforms are running", lambda: self._resume_many([platform_a, platform_b]))
            await checked(
                "Publish S1 schemas",
                lambda: self._ensure_schemas(
                    resolver_url,
                    {
                        S1_INVERTER_TYPE: _s1_inverter_schema(),
                        S1_INSTALLATION_TYPE: _s1_installation_schema(),
                    },
                ),
            )
            await checked("Route installation issuer to Platform A", lambda: self._ensure_platform_route(resolver_url, platform_a, S1_INSTALLATION_TYPE))
            await checked("Route inverter issuer to Platform B", lambda: self._ensure_platform_route(resolver_url, platform_b, S1_INVERTER_TYPE))
            await checked(
                "Anchor original inverter platform for route restoration",
                lambda: self._ensure_platform_anchor(
                    resolver_url,
                    platform_b,
                    f"{platform_b.issuer_id}_s1_origin_anchor",
                    [S1_INVERTER_TYPE],
                ),
            )
            await checked("Restore inverter issuer to Platform B", lambda: self._migrate_issuer(resolver_url, platform_b.issuer_id, platform_b))
            await checked("Cache S1 schemas on Platform A and Platform B", lambda: self._cache_subjects(platform_a, [S1_INSTALLATION_TYPE]))
            await checked("Cache S1 inverter schema on Platform B", lambda: self._cache_subjects(platform_b, [S1_INVERTER_TYPE]))

            successor_platform = await checked(
                "Prepare successor Platform C",
                lambda: self._ensure_successor_platform(platform_b, S1_INVERTER_TYPE),
            )
            await checked(
                "Cache S1 inverter schema on successor Platform C",
                lambda: self._cache_subjects(successor_platform, [S1_INVERTER_TYPE]),
            )
            observations.append(f"Platform A: {platform_a.platform_id}")
            observations.append(f"Platform B: {platform_b.platform_id}")
            observations.append(f"Successor Platform C: {successor_platform.platform_id}")

            run_suffix = _suffix()
            inverter_id = f"{platform_b.issuer_id}-s1-inv-{run_suffix}"
            installation_id = f"{platform_a.issuer_id}-s1-pv-{run_suffix}"

            inverter_revision_1 = await checked(
                "Issue inverter revision 1 on Platform B",
                lambda: self._issue_dpp_with_id(
                    platform_b,
                    inverter_id,
                    S1_INVERTER_TYPE,
                    1,
                    0,
                    _s1_inverter_payload("1.0"),
                ),
            )
            installation_revision = await checked(
                "Issue installation revision with hard and soft inverter references",
                lambda: self._issue_dpp_with_id(
                    platform_a,
                    installation_id,
                    S1_INSTALLATION_TYPE,
                    1,
                    0,
                    _s1_installation_payload(inverter_id, inverter_revision_1["version"]),
                ),
            )

            hard_initial = await checked(
                "Resolve hard reference before target evolution",
                lambda: self._resolve_hard_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, 1, platform_b),
            )
            hard_target_before = hard_initial["target_url"]
            soft_initial = await checked(
                "Resolve soft reference before target evolution",
                lambda: self._resolve_soft_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, platform_b),
            )
            if hard_initial["revision"]["version"] != 1 or soft_initial["current"]["version"] != 1:
                raise RuntimeError("Initial hard and soft references did not resolve to inverter revision 1")

            inverter_revision_2 = await checked(
                "Append inverter revision 2 on Platform B",
                lambda: self._revise_dpp(
                    platform_b,
                    inverter_id,
                    S1_INVERTER_TYPE,
                    1,
                    0,
                    _s1_inverter_payload("2.0"),
                ),
            )
            hard_after_evolution = await checked(
                "Resolve hard reference after target evolution",
                lambda: self._resolve_hard_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, 1, platform_b),
            )
            soft_after_evolution = await checked(
                "Resolve soft reference after target evolution",
                lambda: self._resolve_soft_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, platform_b),
            )
            installation_after_evolution = await checked(
                "Verify installation revision unchanged after target evolution",
                lambda: self._get_json(f"{_platform_url(platform_a)}/dpps/{installation_id}/1"),
            )
            if (
                inverter_revision_2["version"] != 2
                or hard_after_evolution["revision"]["version"] != 1
                or soft_after_evolution["current"]["version"] != 2
                or installation_after_evolution["payload_hash"] != installation_revision["payload_hash"]
                or installation_after_evolution["dpp_payload"] != installation_revision["dpp_payload"]
            ):
                raise RuntimeError("Target evolution did not preserve hard/soft reference semantics")

            await checked(
                "Import inverter revisions into successor Platform C",
                lambda: self._import_revisions(successor_platform, [inverter_revision_1, inverter_revision_2]),
            )
            await checked(
                "Migrate inverter issuer route to successor Platform C",
                lambda: self._migrate_issuer(resolver_url, platform_b.issuer_id, successor_platform),
            )
            hard_after_migration = await checked(
                "Resolve hard reference after issuer migration",
                lambda: self._resolve_hard_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, 1, successor_platform),
            )
            soft_after_migration = await checked(
                "Resolve soft reference after issuer migration",
                lambda: self._resolve_soft_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, successor_platform),
            )
            installation_after_migration = await checked(
                "Verify installation revision unchanged after issuer migration",
                lambda: self._get_json(f"{_platform_url(platform_a)}/dpps/{installation_id}/1"),
            )
            if (
                hard_after_migration["revision"]["version"] != 1
                or soft_after_migration["current"]["version"] != 2
                or hard_after_migration["target_url"] == hard_target_before
                or installation_after_migration["payload_hash"] != installation_revision["payload_hash"]
                or installation_after_migration["dpp_payload"] != installation_revision["dpp_payload"]
            ):
                raise RuntimeError("Issuer migration did not preserve reference semantics")

            await checked("Pause original Platform B", lambda: self._pause_platform(platform_b))
            try:
                hard_without_old = await checked(
                    "Resolve hard reference while original Platform B is paused",
                    lambda: self._resolve_hard_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, 1, successor_platform),
                )
                soft_without_old = await checked(
                    "Resolve soft reference while original Platform B is paused",
                    lambda: self._resolve_soft_reference(resolver_url, S1_INVERTER_TYPE, inverter_id, successor_platform),
                )
                if hard_without_old["revision"]["version"] != 1 or soft_without_old["current"]["version"] != 2:
                    raise RuntimeError("References still depend on the original Platform B")
            finally:
                await checked("Resume original Platform B", lambda: self._resume_platform(platform_b))

            observations.append(f"Installation DPP: {installation_id}")
            observations.append(f"Inverter DPP: {inverter_id}")
            observations.append("Hard reference stayed pinned to inverter revision 1")
            observations.append("Soft reference moved from inverter revision 1 to current revision 2")
            observations.append(f"Resolver route changed from {hard_target_before} to {hard_after_migration['target_url']}")
        finally:
            if platform_b is not None:
                await checked(
                    "Restore inverter issuer route to Platform B",
                    lambda: self._migrate_issuer(resolver_url, platform_b.issuer_id, platform_b),
                )

    async def _run_s5(
        self,
        checked: Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]],
        observations: list[str],
    ) -> None:
        resolver, platforms = await checked("Discover resolver and default platforms", self._require_federation)
        platform_a = _find_platform(platforms, "pv_module")
        platform_b = _find_platform(platforms, "inverter")
        resolver_url = _resolver_url(resolver)
        observations.append(f"Resolver: {resolver.external_url}")
        observations.append(f"PV platform: {platform_a.platform_id} ({platform_a.external_url})")
        observations.append(f"Inverter platform: {platform_b.platform_id} ({platform_b.external_url})")

        await checked("Seed resolver schemas", self._seed_schemas)
        await checked("Ensure platform schemas are cached", lambda: self._cache_subjects(platform_a, ["pv_module"]) )
        await checked("Ensure referenced platform schema is cached", lambda: self._cache_subjects(platform_b, ["inverter"]) )

        inverter_schema = await checked(
            "Load inverter schema 1.0",
            lambda: self._get_schema(resolver_url, "inverter", 1, 0),
        )
        inverter_payload = _payload_from_schema(inverter_schema)
        inverter_payload.update({
            "serial_number": f"INV-{_suffix()}",
            "manufacturer": "Scenario Factory",
            "max_ac_power_watts": 5000,
        })
        inverter_revision = await checked(
            "Issue referenced inverter DPP on Platform B",
            lambda: self._issue_dpp(platform_b, "inverter", 1, 0, inverter_payload),
        )

        pv_schema = await checked(
            "Load PV module schema 1.0",
            lambda: self._get_schema(resolver_url, "pv_module", 1, 0),
        )
        pv_payload = _payload_from_schema(pv_schema)
        pv_payload.update({
            "manufacturer": "Scenario Factory",
            "model": "Offline-PV",
            "serial_number": f"PV-{_suffix()}",
            "components": {
                "inverter": {
                    "$ref": f"inverter/{inverter_revision['dpp_id']}",
                    "version": inverter_revision["version"],
                }
            },
        })
        pv_revision = await checked(
            "Issue PV DPP with hard reference to inverter",
            lambda: self._issue_dpp(platform_a, "pv_module", 1, 0, pv_payload),
        )
        observations.append(f"PV DPP: {pv_revision['dpp_id']}")
        observations.append(f"Inverter DPP: {inverter_revision['dpp_id']} v{inverter_revision['version']}")

        cache_before = await checked(
            "Read Platform A resolution cache before outage",
            lambda: self._get_json(f"{_platform_url(platform_a)}/admin/cache"),
        )
        observations.append(f"Platform A cache entries before outage: {len(cache_before)}")

        await checked("Pause referenced Platform B", lambda: self._pause_platform(platform_b))
        try:
            detail = await checked(
                "Fetch PV DPP detail while Platform B is paused",
                lambda: self._get_json(f"{_platform_url(platform_a)}/dpps/{pv_revision['dpp_id']}"),
            )
            observations.append(f"PV detail remained readable with {len(detail.get('revisions', []))} revision(s).")
        finally:
            await checked("Restore referenced Platform B", lambda: self._resume_platform(platform_b))

    async def _run_s4(
        self,
        checked: Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]],
        observations: list[str],
    ) -> str | None:
        """Run the canonical S4 query-execution workload in-process.

        The workload owns the deterministic six-platform data set and compares
        predicate/traverse queries in INDEXED and ON_DEMAND modes.  The Factory
        remains the HTTP entry point but does not duplicate or shell out to that
        implementation.
        """
        result = await checked("Execute S4 query evaluation workload", self._execute_s4_workload)
        observations.extend(result.observations)
        if not result.success:
            error = next((step.error for step in result.steps if step.error), "S4 query evaluation reported failed checks")
            await checked(
                "Verify S4 query equivalence",
                lambda: _raise_s4_workload_failure(result, error),
            )

        for workload_step in result.steps:
            await checked(
                workload_step.name,
                lambda step=workload_step: _assert_workload_step_passed(step),
            )
        return result.report_md

    async def _execute_s4_workload(self) -> Any:
        """Load the reusable workload package only when S4 is requested."""
        try:
            from workload.scenarios.s4 import run_s4_scenario
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "S4 requires the workload-generator package. Install the Factory with its workload dependency."
            ) from exc

        factory_url = os.getenv("DPP_FACTORY_URL", "http://127.0.0.1:8000")
        scale = os.getenv("DPP_S4_SCALE", "small")
        try:
            seed = int(os.getenv("DPP_S4_SEED", "42"))
        except ValueError as exc:
            raise RuntimeError("DPP_S4_SEED must be an integer") from exc
        output_dir = os.getenv("DPP_SCENARIO_OUTPUT_DIR")
        return await run_s4_scenario(
            factory_url=factory_url,
            seed=seed,
            scale=scale,
            output_dir=None if output_dir is None else Path(output_dir),
        )

    async def _run_s2(
        self,
        checked: Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]],
        observations: list[str],
    ) -> None:
        resolver, platforms = await checked("Discover resolver and inverter platform", self._require_federation)
        resolver_url = _resolver_url(resolver)
        platform_b = _find_platform(platforms, "inverter")
        await checked("Ensure inverter platform is running", lambda: self._resume_platform(platform_b))
        await checked("Seed resolver schemas", self._seed_schemas)
        await checked("Cache inverter schema on Platform B", lambda: self._cache_subjects(platform_b, ["inverter"]) )

        schemas = await checked(
            "Read current inverter schemas from resolver",
            lambda: self._get_json(f"{resolver_url}/schemas/inverter"),
        )
        if not schemas:
            raise RuntimeError("Resolver returned no inverter schemas")
        current = _latest_schema(schemas)
        current_major = _dto_value(current, "majorVersion", "major_version")
        current_minor = _dto_value(current, "minorVersion", "minor_version")
        current_schema = _dto_value(current, "schemaDocument", "schema_document")

        base_payload = _payload_from_schema(current_schema)
        base_payload.update({
            "serial_number": f"INV-S2-{_suffix()}",
            "manufacturer": "Scenario Factory",
            "max_ac_power_watts": 4300,
        })
        revision_1 = await checked(
            "Issue inverter revision under current schema",
            lambda: self._issue_dpp(platform_b, "inverter", current_major, current_minor, base_payload),
        )

        marker = f"scenario_required_{_suffix()}"
        evolved_schema = copy.deepcopy(current_schema)
        evolved_schema["$id"] = f"https://schemas.dpp.eu/inverter/{current_major + 1}.0"
        evolved_schema.setdefault("properties", {})[marker] = {"type": "string"}
        required = evolved_schema.setdefault("required", [])
        if marker not in required:
            required.append(marker)

        await checked(
            "Publish inverter schema major update",
            lambda: self._publish_schema(resolver_url, "inverter", current_major + 1, 0, evolved_schema),
        )
        await checked("Cache evolved schema on Platform B", lambda: self._cache_subjects(platform_b, ["inverter"]) )

        evolved_payload = copy.deepcopy(base_payload)
        evolved_payload[marker] = "present"
        revision_2 = await checked(
            "Create new inverter revision under evolved schema",
            lambda: self._revise_dpp(platform_b, revision_1["dpp_id"], "inverter", current_major + 1, 0, evolved_payload),
        )
        await checked(
            "Verify original schema remains retrievable",
            lambda: self._get_schema(resolver_url, "inverter", current_major, current_minor),
        )
        observations.append(f"Original DPP revision: {revision_1['dpp_id']} v{revision_1['version']}")
        observations.append(f"Evolved DPP revision: {revision_2['dpp_id']} v{revision_2['version']}")
        observations.append(f"New schema version: inverter/{current_major + 1}.0 with required field `{marker}`")

    async def _run_s3(
        self,
        checked: Callable[[str, Callable[[], Awaitable[Any]]], Awaitable[Any]],
        observations: list[str],
    ) -> None:
        resolver, _platforms = await checked("Discover resolver", self._require_federation)
        resolver_url = _resolver_url(resolver)
        suffix = _suffix()
        subject_a = f"cycle_a_{suffix}"
        subject_b = f"cycle_b_{suffix}"

        await checked("Register cycle subject types", lambda: self._ensure_subject_types(resolver_url, [subject_a, subject_b]))
        schema_a = _reference_schema(subject_a, subject_b)
        schema_b = _reference_schema(subject_b, subject_a)
        await checked(
            "Publish acyclic first schema A -> B",
            lambda: self._publish_schema(resolver_url, subject_a, 1, 0, schema_a),
        )
        rejection = await checked(
            "Reject cyclic schema B -> A",
            lambda: self._expect_schema_rejection(resolver_url, subject_b, schema_b),
        )
        schemas_b = await checked(
            "Confirm rejected schema is not stored",
            lambda: self._get_json(f"{resolver_url}/schemas/{subject_b}"),
        )
        if schemas_b:
            raise RuntimeError(f"Rejected subject {subject_b} unexpectedly has {len(schemas_b)} schema(s)")
        observations.append(f"Rejected subject type: {subject_b}")
        observations.append(f"Resolver rejection: HTTP {rejection['status_code']} - {rejection['body']}")

    async def _require_federation(self) -> tuple[Any, list[PlatformRecord]]:
        resolver = await self.state.get_resolver()
        if not resolver or not resolver.external_url:
            raise RuntimeError("Resolver is not available in the factory state")
        platforms = await self.state.list_platforms()
        running = [platform for platform in platforms if platform.status in (PlatformStatus.RUNNING, PlatformStatus.PAUSED)]
        if not running:
            raise RuntimeError("No DPP platforms are available in the factory state")
        return resolver, running

    async def _resume_many(self, platforms: list[PlatformRecord]) -> None:
        for platform in platforms:
            await self._resume_platform(platform)

    async def _ensure_schemas(self, resolver_url: str, schemas: dict[str, dict]) -> None:
        await self._ensure_subject_types(resolver_url, list(schemas.keys()))
        for subject_type, schema in schemas.items():
            try:
                await self._get_schema(resolver_url, subject_type, 1, 0)
            except Exception:
                await self._publish_schema(resolver_url, subject_type, 1, 0, schema)

    async def _ensure_platform_route(
        self,
        resolver_url: str,
        platform: PlatformRecord,
        subject_type: str,
    ) -> None:
        mappings = await self._get_json(f"{resolver_url}/admin/platforms")
        mapping = next((item for item in mappings if _dto_value(item, "issuerId", "issuer_id") == platform.issuer_id), None)
        if mapping is None:
            raise RuntimeError(f"Resolver has no mapping for issuer {platform.issuer_id}")
        subject_types = set(_dto_value(mapping, "subjectTypes", "subject_types"))
        if subject_type in subject_types:
            return
        await self._post_json(f"{resolver_url}/admin/platforms/{platform.issuer_id}/subject-types/{subject_type}", {})

    async def _ensure_platform_anchor(
        self,
        resolver_url: str,
        platform: PlatformRecord,
        anchor_issuer_id: str,
        subject_types: list[str],
    ) -> None:
        """Register a harmless alias row so the migrated issuer can be restored.

        Resolver migration validates target platforms against existing registry rows.
        Once S1 moves issuerB from Platform B to Platform C, the issuerB row no longer
        names Platform B. This anchor keeps Platform B discoverable as a migration target
        while all real references continue to use the issuerB route.
        """
        mappings = await self._get_json(f"{resolver_url}/admin/platforms")
        resolution_url = f"{_platform_url(platform).rstrip('/')}/dpps/{{dppId}}"
        mapping = next(
            (item for item in mappings if (item.get("issuerId") or item.get("issuer_id")) == anchor_issuer_id),
            None,
        )
        if mapping is None:
            await self._post_json(f"{resolver_url}/admin/platforms/register", {
                "platform": platform.platform_id,
                "resolution_url": resolution_url,
                "issuer_id": anchor_issuer_id,
                "subject_types": list(dict.fromkeys(subject_types)),
            })
            return

        existing_platform = mapping.get("platform")
        existing_url = mapping.get("resolutionUrl") or mapping.get("resolution_url")
        if existing_platform != platform.platform_id or existing_url != resolution_url:
            raise RuntimeError(
                f"Resolver anchor {anchor_issuer_id} points to {existing_platform} ({existing_url}), "
                f"expected {platform.platform_id} ({resolution_url})"
            )

        existing_subject_types = set(mapping.get("subjectTypes") or mapping.get("subject_types") or [])
        for subject_type in subject_types:
            if subject_type not in existing_subject_types:
                await self._post_json(
                    f"{resolver_url}/admin/platforms/{anchor_issuer_id}/subject-types/{subject_type}",
                    {},
                )

    async def _ensure_successor_platform(
        self,
        source_platform: PlatformRecord,
        subject_type: str,
    ) -> PlatformRecord:
        successor_issuer_prefix = f"{source_platform.issuer_id}_s1_successor"
        platforms = await self.state.list_platforms()
        for platform in _s1_successor_records(platforms, successor_issuer_prefix, subject_type):
            await self._resume_platform(platform)
            if await self._wait_for_revision_import(platform, attempts=3, delay_seconds=1.0):
                return platform

        last_created: PlatformRecord | None = None
        for stack in _successor_stack_order(source_platform.stack):
            successor = await self.platform_service.spawn_platform(
                stack,
                _next_successor_issuer(successor_issuer_prefix, platforms),
                [subject_type],
            )
            platforms.append(successor)
            last_created = successor
            if await self._wait_for_revision_import(successor, attempts=12, delay_seconds=1.0):
                return successor

        if last_created is None:
            raise RuntimeError("Could not prepare a successor platform for S1")
        raise RuntimeError(
            "Could not prepare an import-capable successor platform for S1. "
            "Rebuild platform images so /admin/import-revisions is available before rerunning the scenario."
        )

    async def _migrate_issuer(
        self,
        resolver_url: str,
        issuer_id: str,
        target_platform: PlatformRecord,
    ) -> dict:
        return await self._post_json(f"{resolver_url}/admin/platforms/{issuer_id}/migrate", {
            "platform": target_platform.platform_id,
            "new_resolution_url": f"{_platform_url(target_platform).rstrip('/')}/dpps/{{dppId}}",
        })

    async def _seed_schemas(self) -> None:
        summary = await self.schema_seed_service.seed_schemas()
        hard_failures = [
            failure for failure in summary.failed
            if "immutable" not in failure.lower() and "400" not in failure
        ]
        if hard_failures:
            raise RuntimeError(f"Schema seeding failed: {hard_failures}")

    async def _cache_subjects(self, platform: PlatformRecord, subject_types: list[str]) -> None:
        await self._ensure_platform_subject_types(platform, subject_types)
        for subject_type in subject_types:
            await self._post_json(f"{_platform_url(platform)}/schemas/{subject_type}/cacheSchema", {})

    async def _ensure_platform_subject_types(self, platform: PlatformRecord, subject_types: list[str]) -> None:
        for subject_type in subject_types:
            response = await self._post_raw(f"{_platform_url(platform)}/admin/subject-types", {
                "name": subject_type,
                "description": subject_type.replace("_", " ").title(),
            })
            if response.status_code in (200, 201, 409):
                continue
            if response.status_code == 400 and _looks_like_duplicate_subject_type(response.text):
                continue
            response.raise_for_status()

    async def _platform_supports_revision_import(self, platform: PlatformRecord) -> bool:
        """Probe whether a successor can receive copied revisions for S1 migration."""
        response = await self._post_raw(f"{_platform_url(platform)}/admin/import-revisions", [])
        if 200 <= response.status_code < 300:
            return True
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    async def _wait_for_revision_import(
        self,
        platform: PlatformRecord,
        *,
        attempts: int,
        delay_seconds: float,
    ) -> bool:
        """Wait for a newly spawned successor to expose S1's admin import route.

        The Factory waits for container health before returning a platform, but
        S1 can still probe the admin route during a short startup gap. A 404 is a
        real capability miss and stays terminal; transient HTTP failures are
        retried so the frontend and CLI scenario paths behave consistently.
        """
        for attempt in range(1, attempts + 1):
            try:
                return await self._platform_supports_revision_import(platform)
            except httpx.HTTPError:
                if attempt == attempts:
                    return False
                await asyncio.sleep(delay_seconds)
        return False

    async def _pause_platform(self, platform: PlatformRecord) -> None:
        await self.platform_service.pause_platform(platform.platform_id)

    async def _resume_platform(self, platform: PlatformRecord) -> None:
        latest = await self.platform_service.get_platform(platform.platform_id)
        if latest and latest.status == PlatformStatus.PAUSED:
            await self.platform_service.resume_platform(platform.platform_id)

    async def _issue_dpp(
        self,
        platform: PlatformRecord,
        subject_type: str,
        major: int,
        minor: int,
        payload: dict,
    ) -> dict:
        return await self._post_json(f"{_platform_url(platform)}/dpps/issue", {
            "schema_version": {
                "subject_type": subject_type,
                "major_version": major,
                "minor_version": minor,
            },
            "dpp_payload": payload,
        })

    async def _issue_dpp_with_id(
        self,
        platform: PlatformRecord,
        dpp_id: str,
        subject_type: str,
        major: int,
        minor: int,
        payload: dict,
    ) -> dict:
        return await self._post_json(f"{_platform_url(platform)}/dpps/issue", {
            "dpp_id": dpp_id,
            "schema_version": {
                "subject_type": subject_type,
                "major_version": major,
                "minor_version": minor,
            },
            "dpp_payload": payload,
        })

    async def _revise_dpp(
        self,
        platform: PlatformRecord,
        dpp_id: str,
        subject_type: str,
        major: int,
        minor: int,
        payload: dict,
    ) -> dict:
        return await self._post_json(f"{_platform_url(platform)}/dpps/{dpp_id}/revise", {
            "schema_version": {
                "subject_type": subject_type,
                "major_version": major,
                "minor_version": minor,
            },
            "dpp_payload": payload,
        })

    async def _get_schema(self, resolver_url: str, subject_type: str, major: int, minor: int) -> dict:
        dto = await self._get_json(f"{resolver_url}/schemas/{subject_type}/{major}/{minor}")
        return _dto_value(dto, "schemaDocument", "schema_document")

    async def _publish_schema(
        self,
        resolver_url: str,
        subject_type: str,
        major: int,
        minor: int,
        schema_document: dict,
    ) -> dict:
        return await self._post_json(f"{resolver_url}/schemas", {
            "subject_type": subject_type,
            "major_version": major,
            "minor_version": minor,
            "schema_document": schema_document,
        })

    async def _ensure_subject_types(self, resolver_url: str, subject_types: list[str]) -> None:
        for subject_type in subject_types:
            response = await self._post_raw(f"{resolver_url}/admin/subject-types", {
                "name": subject_type,
                "description": subject_type.replace("_", " ").title(),
            })
            if response.status_code not in (200, 201, 400, 409):
                raise RuntimeError(f"Subject type {subject_type} rejected: HTTP {response.status_code} - {response.text}")

    async def _expect_schema_rejection(self, resolver_url: str, subject_type: str, schema_document: dict) -> dict:
        response = await self._post_raw(f"{resolver_url}/schemas", {
            "subject_type": subject_type,
            "major_version": 1,
            "minor_version": 0,
            "schema_document": schema_document,
        })
        if response.status_code < 400:
            raise RuntimeError(f"Expected resolver to reject cyclic schema, got HTTP {response.status_code}")
        return {"status_code": response.status_code, "body": response.text}

    async def _import_revisions(self, platform: PlatformRecord, revisions: list[dict]) -> list[dict]:
        """Copy already-issued revisions into the S1 successor platform.

        The preferred route is the admin import endpoint because issuer migration is
        a relocation of existing revision history, not a fresh issue/revise path.
        During live local runs, however, an already-built successor image may not yet
        contain that endpoint. A 404 therefore falls back to the public issue/revise
        APIs and verifies that payload hashes remain identical to the source revisions.
        """
        response = await self._post_raw(f"{_platform_url(platform)}/admin/import-revisions", revisions)
        if response.status_code == 404:
            self._assert_public_replay_can_preserve_ids(platform, revisions)
            return await self._replay_imported_revisions(platform, revisions)

        response.raise_for_status()
        if not response.content:
            return []
        return response.json()

    async def _replay_imported_revisions(self, platform: PlatformRecord, revisions: list[dict]) -> list[dict]:
        """Recreate imported revisions through issue/revise when admin import is absent."""
        imported_revisions: list[dict] = []
        for revision in sorted(revisions, key=lambda item: (item["dpp_id"], item["version"])):
            if revision["version"] < 1:
                raise RuntimeError(f"Cannot import non-positive revision version {revision['version']}")

            if revision["version"] == 1:
                imported = await self._issue_imported_revision(platform, revision)
            else:
                imported = await self._revise_imported_revision(platform, revision)

            self._assert_imported_revision_matches(revision, imported)
            imported_revisions.append(imported)
        return imported_revisions

    def _assert_public_replay_can_preserve_ids(self, platform: PlatformRecord, revisions: list[dict]) -> None:
        """Ensure issue/revise fallback can satisfy the platform issuer-prefix rule."""
        expected_prefix = f"{platform.issuer_id}-"
        mismatched = next(
            (revision["dpp_id"] for revision in revisions if not revision["dpp_id"].startswith(expected_prefix)),
            None,
        )
        if mismatched is not None:
            raise RuntimeError(
                "Platform is missing /admin/import-revisions and public replay cannot preserve "
                f"source DPP ID {mismatched!r}: target platform {platform.platform_id} uses issuer "
                f"prefix {expected_prefix!r}. Rebuild the platform image with the admin import "
                "endpoint or choose an import-capable successor."
            )

    async def _issue_imported_revision(self, platform: PlatformRecord, revision: dict) -> dict:
        """Issue revision 1 with the source DPP ID while replaying an import."""
        return await self._post_json(f"{_platform_url(platform)}/dpps/issue", {
            "dpp_id": revision["dpp_id"],
            "schema_version": revision["schema_version"],
            "dpp_payload": revision["dpp_payload"],
        })

    async def _revise_imported_revision(self, platform: PlatformRecord, revision: dict) -> dict:
        """Append the source revision version while replaying an import."""
        return await self._post_json(f"{_platform_url(platform)}/dpps/{revision['dpp_id']}/revise", {
            "version": revision["version"],
            "schema_version": revision["schema_version"],
            "dpp_payload": revision["dpp_payload"],
        })

    def _assert_imported_revision_matches(self, expected: dict, actual: dict) -> None:
        """Guard S1 against a fallback replay that mutates revision identity or content."""
        for key in ("dpp_id", "version", "schema_version", "dpp_payload", "payload_hash"):
            if actual.get(key) != expected.get(key):
                raise RuntimeError(
                    "Fallback import changed revision content: "
                    f"field {key} expected {expected.get(key)!r}, got {actual.get(key)!r}"
                )

    async def _resolve_hard_reference(
        self,
        resolver_url: str,
        subject_type: str,
        dpp_id: str,
        version: int,
        platform: PlatformRecord,
    ) -> dict:
        resolved = await self._resolve_and_fetch(resolver_url, subject_type, dpp_id, version, platform)
        return {
            "target_url": resolved["target_url"],
            "revision": resolved["data"],
        }

    async def _resolve_soft_reference(
        self,
        resolver_url: str,
        subject_type: str,
        dpp_id: str,
        platform: PlatformRecord,
    ) -> dict:
        resolved = await self._resolve_and_fetch(resolver_url, subject_type, dpp_id, None, platform)
        revisions = resolved["data"].get("revisions", [])
        if not revisions:
            raise RuntimeError(f"Soft resolution returned no revisions for {dpp_id}")
        return {
            "target_url": resolved["target_url"],
            "current": max(revisions, key=lambda revision: revision["version"]),
        }

    async def _resolve_and_fetch(
        self,
        resolver_url: str,
        subject_type: str,
        dpp_id: str,
        version: int | None,
        platform: PlatformRecord,
    ) -> dict:
        path = f"/{subject_type}/{dpp_id}" if version is None else f"/{subject_type}/{dpp_id}/{version}"
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.get(f"{resolver_url}{path}")
        if not response.is_redirect:
            response.raise_for_status()
            raise RuntimeError(f"Resolver did not redirect {path}: HTTP {response.status_code}")

        target_url = response.headers["location"]
        parsed = httpx.URL(target_url)
        data = await self._get_json(f"{_platform_url(platform).rstrip('/')}{parsed.path}")
        return {
            "target_url": target_url,
            "data": data,
        }

    async def _get_json(self, url: str) -> Any:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def _post_json(self, url: str, body: Any) -> Any:
        response = await self._post_raw(url, body)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def _post_raw(self, url: str, body: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=20.0) as client:
            return await client.post(url, json=body)


def _payload_from_schema(schema: dict) -> dict:
    return _empty_value(schema)


def _s1_inverter_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://dpp.example.org/schemas/s1-inverter",
        "title": "S1 Inverter",
        "type": "object",
        "properties": {
            "serialNumber": {"type": "string"},
            "manufacturer": {"type": "string"},
            "ratedPowerKw": {"type": "number"},
            "firmwareVersion": {"type": "string"},
        },
        "required": ["serialNumber", "manufacturer", "ratedPowerKw", "firmwareVersion"],
        "additionalProperties": False,
    }


def _s1_installation_schema() -> dict:
    ref_pattern = f"^{S1_INVERTER_TYPE}/[^/]+$"
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://dpp.example.org/schemas/s1-pv-installation",
        "title": "S1 PV Installation",
        "type": "object",
        "properties": {
            "installationId": {"type": "string"},
            "site": {"type": "string"},
            "inverterEvidenceRef": {
                "type": "object",
                "x-dpp-reference": S1_INVERTER_TYPE,
                "properties": {
                    "$ref": {"type": "string", "pattern": ref_pattern},
                    "version": {"type": "integer", "minimum": 1},
                    "mode": {"const": "hard"},
                },
                "required": ["$ref", "version", "mode"],
                "additionalProperties": False,
            },
            "inverterCurrentRef": {
                "type": "object",
                "properties": {
                    "$ref": {"type": "string", "pattern": ref_pattern},
                    "mode": {"const": "soft"},
                },
                "required": ["$ref", "mode"],
                "additionalProperties": False,
            },
        },
        "required": ["installationId", "site", "inverterEvidenceRef", "inverterCurrentRef"],
        "additionalProperties": False,
    }


def _s1_inverter_payload(firmware_version: str) -> dict:
    return {
        "serialNumber": "INV-001",
        "manufacturer": "InverterCo",
        "ratedPowerKw": 10,
        "firmwareVersion": firmware_version,
    }


def _s1_installation_payload(inverter_id: str, hard_version: int) -> dict:
    ref = f"{S1_INVERTER_TYPE}/{inverter_id}"
    return {
        "installationId": "PV-001",
        "site": "Demo Site",
        "inverterEvidenceRef": {
            "$ref": ref,
            "version": hard_version,
            "mode": "hard",
        },
        "inverterCurrentRef": {
            "$ref": ref,
            "mode": "soft",
        },
    }


def _empty_value(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return None
    if "default" in schema:
        return copy.deepcopy(schema["default"])
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    if "enum" in schema and schema["enum"]:
        return copy.deepcopy(schema["enum"][0])
    if "oneOf" in schema and schema["oneOf"]:
        return _empty_value(schema["oneOf"][0])
    if "anyOf" in schema and schema["anyOf"]:
        return _empty_value(schema["anyOf"][0])
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0])
    if schema_type == "object" or "properties" in schema:
        return {
            key: _empty_value(value)
            for key, value in schema.get("properties", {}).items()
        }
    if schema_type == "array":
        return []
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "string":
        return ""
    return None


def _reference_schema(subject_type: str, target_subject_type: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://schemas.dpp.eu/{subject_type}/1.0",
        "title": subject_type,
        "type": "object",
        "properties": {
            "serial_number": {"type": "string"},
            "target": {
                "type": "object",
                "x-dpp-reference": target_subject_type,
                "properties": {
                    "$ref": {"type": "string"},
                    "version": {"type": "integer"},
                },
                "required": ["$ref"],
            },
        },
        "required": ["serial_number"],
    }


def _find_platform(platforms: list[PlatformRecord], subject_type: str) -> PlatformRecord:
    for platform in platforms:
        if subject_type in platform.subject_types:
            return platform
    raise RuntimeError(f"No platform supports subject type {subject_type}")


def _s1_successor_records(
    platforms: list[PlatformRecord],
    issuer_prefix: str,
    subject_type: str,
) -> list[PlatformRecord]:
    """Return existing S1 successors without confusing them with source platforms."""
    return [
        platform
        for platform in platforms
        if platform.issuer_id.startswith(issuer_prefix) and subject_type in platform.subject_types
    ]


def _successor_stack_order(source_stack: str) -> list[str]:
    """Try the opposite implementation first, then the source stack as a fallback."""
    opposite = "spring-postgres" if source_stack != "spring-postgres" else "fastapi-mongo"
    return list(dict.fromkeys([opposite, source_stack]))


def _next_successor_issuer(issuer_prefix: str, platforms: list[PlatformRecord]) -> str:
    """Choose a unique resolver-registration alias for a migration successor."""
    used_issuers = {platform.issuer_id for platform in platforms}
    if issuer_prefix not in used_issuers:
        return issuer_prefix

    index = 2
    while f"{issuer_prefix}_{index}" in used_issuers:
        index += 1
    return f"{issuer_prefix}_{index}"


def _resolver_url(resolver: Any) -> str:
    return resolver.internal_url or resolver.external_url


def _platform_url(platform: PlatformRecord) -> str:
    return platform.internal_url or platform.external_url


def _latest_schema(schemas: list[dict]) -> dict:
    return max(
        schemas,
        key=lambda schema: (
            _dto_value(schema, "majorVersion", "major_version"),
            _dto_value(schema, "minorVersion", "minor_version"),
        ),
    )


def _dto_value(dto: dict, camel_key: str, snake_key: str) -> Any:
    if camel_key in dto:
        return dto[camel_key]
    return dto[snake_key]


def _looks_like_duplicate_subject_type(text: str) -> bool:
    lower_text = text.lower()
    return "subject type" in lower_text and "already" in lower_text and "exist" in lower_text


def _suffix() -> str:
    return datetime.now(UTC).strftime("%H%M%S%f")


async def _assert_workload_step_passed(step: Any) -> None:
    if step.status != "passed":
        raise RuntimeError(step.error or f"Workload step {step.name!r} did not pass")


async def _raise_s4_workload_failure(result: Any, error: str) -> None:
    raise S4WorkloadFailure(result.report_md, error)


def _build_report(
    scenario_id: str,
    status: str,
    elapsed_ms: float,
    steps: list[ScenarioStep],
    observations: list[str],
) -> str:
    title = {
        "s1": "S1: Federated Reference Stability Under Target Evolution and Issuer Migration",
        "s2": "S2: Independent Schema Evolution",
        "s3": "S3: Schema-Level Cycle Rejection",
        "s4": "S4: Query Execution",
        "s5": "S5: Offline Validation After Platform Unavailability",
    }.get(scenario_id, scenario_id.upper())
    lines = [
        f"# {title}",
        "",
        f"- Status: `{status}`",
        f"- Duration: `{elapsed_ms} ms`",
    ]
    if scenario_id == "s5":
        lines.extend([
            "- Evaluation scope: `supplemental only; not part of the actual evaluation`",
            "- Purpose: `probe whether offline validation may be interesting for future work`",
        ])
    lines.extend([
        "",
        "## Steps",
    ])
    for step in steps:
        suffix = f" - {step.error}" if step.error else ""
        lines.append(f"- `{step.status}` {step.name}{suffix}")
    if observations:
        lines.extend(["", "## Observations"])
        lines.extend(f"- {item}" for item in observations)
    lines.extend(["", "## Raw Status", "```json", json.dumps({
        "scenario_id": scenario_id,
        "status": status,
        "steps": [step.model_dump() for step in steps],
        "observations": observations,
    }, indent=2), "```"])
    return "\n".join(lines)
