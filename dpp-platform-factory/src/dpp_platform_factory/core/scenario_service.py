import copy
import httpx
import json
import time
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from .platform_service import PlatformService
from .schema_seed_service import SchemaSeedService
from .state import FactoryState, PlatformRecord, PlatformStatus
from ..api.api_models import ScenarioStatus, ScenarioStep

SCENARIO_IDS = ("s2", "s3", "s4")


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
            if scenario_id == "s2":
                await self._run_s2(checked, observations)
            elif scenario_id == "s3":
                await self._run_s3(checked, observations)
            elif scenario_id == "s4":
                await self._run_s4(checked, observations)
            else:
                raise ValueError(f"Unknown scenario: {scenario_id}")
            status = "passed"
        except Exception as exc:
            status = "failed"
            observations.append(f"Failure: {exc}")

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        report = _build_report(scenario_id, status, elapsed_ms, steps, observations)
        return ScenarioStatus(
            scenario_id=scenario_id,
            status=status,
            steps=steps,
            report_md=report,
        )

    async def _run_s4(
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

    async def _get_json(self, url: str) -> Any:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def _post_json(self, url: str, body: dict) -> Any:
        response = await self._post_raw(url, body)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def _post_raw(self, url: str, body: dict) -> httpx.Response:
        async with httpx.AsyncClient(timeout=20.0) as client:
            return await client.post(url, json=body)


def _payload_from_schema(schema: dict) -> dict:
    return _empty_value(schema)


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


def _build_report(
    scenario_id: str,
    status: str,
    elapsed_ms: float,
    steps: list[ScenarioStep],
    observations: list[str],
) -> str:
    title = {
        "s2": "S2: Independent Schema Evolution",
        "s3": "S3: Schema-Level Cycle Rejection",
        "s4": "S4: Offline Validation After Platform Unavailability",
    }.get(scenario_id, scenario_id.upper())
    lines = [
        f"# {title}",
        "",
        f"- Status: `{status}`",
        f"- Duration: `{elapsed_ms} ms`",
    ]
    if scenario_id == "s4":
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
