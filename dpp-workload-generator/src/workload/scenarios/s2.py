import structlog
from pathlib import Path
from typing import Optional

from .reporter import ScenarioReporter
from ..clients import (
    DppNotFoundError,
    ResolverClient,
    PlatformClient,
    IssueDppSpec,
    DppSchemaVersion,
    SchemaValidationError,
)
from ..federation import FederationClient
from ..payloads import generate_seed_payload, ReferenceSpec
from ..seed_schemas import canonical_seed_schema

logger = structlog.get_logger(__name__)

async def run_s2(factory_url: str, seed: int, output_dir: Optional[Path] = None) -> bool:
    """Scenario S2: Independent Schema Evolution"""
    reporter = ScenarioReporter("s2", "Independent Schema Evolution", output_dir=output_dir)

    async with FederationClient() as fed_client:
        resolver = None
        battery_resp = None
        pv_resp = None
        battery_schema_v1 = None
        battery_schema_v2 = None
        pv_schema_v1 = None

        with reporter.step("Setup federation", "Federation discovered and reset"):
            fed = await fed_client.discover(factory_url)
            await fed_client.reset_all_platforms(factory_url)
            resolver_url = await fed_client.resolver_url()
            resolver = ResolverClient(resolver_url)

            await resolver.ensure_subject_type("battery")
            await resolver.ensure_subject_type("pv_module")
            battery_schema_v1 = await _ensure_compatible_seed_schema(resolver, "battery")
            pv_schema_v1 = await _ensure_compatible_seed_schema(resolver, "pv_module")

            reporter.record_observation(
                "Federation ready, compatible battery and pv_module schemas available",
                True,
            )

        try:
            if resolver is None:
                raise RuntimeError("Setup failed: resolver not available")

            platform_b = await fed_client.find_platform_for_subject_type("battery")
            with reporter.step("Issue battery DPP under baseline schema", "battery DPP created with a compatible baseline schema"):
                if battery_schema_v1 is None:
                    raise RuntimeError("Setup failed: battery schema not available")
                async with PlatformClient(platform_b) as client:
                    battery_spec = IssueDppSpec(
                        schema_version=battery_schema_v1,
                        dpp_payload=generate_seed_payload("battery", seed=seed)
                    )
                    battery_resp = await client.issue_dpp(battery_spec)
                    reporter.record_observation(f"Battery DPP issued: {battery_resp.dpp_id}", True)

            platform_a = await fed_client.find_platform_for_subject_type("pv_module")
            with reporter.step("Issue PV-module DPP with hard dep pinned to battery v1", "PV-module DPP created with hard ref"):
                if battery_resp is None:
                    raise RuntimeError("Battery DPP was not issued")
                if pv_schema_v1 is None:
                    raise RuntimeError("Setup failed: pv_module schema not available")
                async with PlatformClient(platform_a) as client:
                    pv_spec = IssueDppSpec(
                        schema_version=pv_schema_v1,
                        dpp_payload=generate_seed_payload("pv_module", seed=seed + 1, hard_refs={
                            "battery": ReferenceSpec(subject_type="battery", dpp_id=battery_resp.dpp_id,
                                                     version=battery_resp.version)
                        })
                    )
                    pv_resp = await client.issue_dpp(pv_spec)
                    reporter.record_observation(f"PV-module DPP issued: {pv_resp.dpp_id}", True)

            with reporter.step("Verify PV-module is valid (baseline)", "GET PV-module returns 200"):
                if pv_resp is None:
                    raise RuntimeError("PV-module DPP was not issued")
                async with PlatformClient(platform_a) as client:
                    await client.get_revision(pv_resp.dpp_id, pv_resp.version)
                    reporter.record_observation("PV-module valid against schema 1.0", True)

            with reporter.step("Publish battery schema 2.0 (major update)", "schema published, marked as major"):
                if battery_schema_v1 is None:
                    raise RuntimeError("Setup failed: battery schema not available")
                # Build v2.0 on top of the actual v1.0 seed schema to keep existing fields valid.
                battery_schema_v2 = await _ensure_battery_schema_with_cell_chemistry(
                    resolver,
                    battery_schema_v1,
                )
                reporter.record_observation("Battery schema 2.0 published with breaking change (required cell_chemistry)", True)

            with reporter.step("Verify battery schema 1.0 is still retrievable", "historical schemas remain accessible"):
                if battery_schema_v1 is None:
                    raise RuntimeError("Setup failed: battery schema not available")
                schema_v1 = await resolver.get_schema(
                    "battery",
                    battery_schema_v1.major_version,
                    battery_schema_v1.minor_version,
                )
                is_v1 = "cell_chemistry" not in schema_v1.get("required", [])
                reporter.record_observation("Schema 1.0 still available without cell_chemistry", is_v1)

            with reporter.step("Verify existing PV-module DPP remains valid", "PV-module's pinned battery still valid"):
                if pv_resp is None:
                    raise RuntimeError("PV-module DPP was not issued")
                async with PlatformClient(platform_a) as client:
                    await client.get_revision(pv_resp.dpp_id, pv_resp.version)
                    reporter.record_observation("Existing PV-module remains valid", True)

            with reporter.step("Issue a new battery DPP under schema 2.0", "new battery DPP satisfies 2.0 constraints"):
                if battery_schema_v2 is None:
                    raise RuntimeError("Battery schema 2.0 was not published")
                async with PlatformClient(platform_b) as client:
                    payload_v2 = generate_seed_payload("battery", seed=seed + 2)
                    payload_v2["cell_chemistry"] = "Li-ion"
                    battery_v2_resp = await client.issue_dpp(IssueDppSpec(
                        schema_version=battery_schema_v2,
                        dpp_payload=payload_v2
                    ))
                    reporter.record_observation(f"New Battery DPP issued under 2.0: {battery_v2_resp.dpp_id}", True)

            with reporter.step("Try issuing a new battery DPP under 2.0 missing required field", "rejected by schema validation"):
                if battery_schema_v2 is None:
                    raise RuntimeError("Battery schema 2.0 was not published")
                async with PlatformClient(platform_b) as client:
                    try:
                        await client.issue_dpp(IssueDppSpec(
                            schema_version=battery_schema_v2,
                            dpp_payload=generate_seed_payload("battery", seed=seed + 3)  # missing cell_chemistry
                        ))
                        reporter.record_observation("Unexpectedly accepted invalid payload", False)
                    except SchemaValidationError as e:
                        reporter.record_observation(f"Correctly rejected schema-invalid payload: {str(e)[:100]}", True)

        except Exception as e:
            logger.error("s2_step_failed", error=str(e))

    report_path = reporter.finalize()
    logger.info("s2_complete", report_path=str(report_path))
    return reporter.result.outcome == "PASSED"


async def _ensure_compatible_seed_schema(
    resolver: ResolverClient,
    subject_type: str,
) -> DppSchemaVersion:
    """Return a schema version that accepts the canonical S2 seed payload.

    Resolver schemas are immutable and shared across scenario runs. If another
    scenario already owns ``subject_type/1.0`` with a narrower schema, S2 must
    publish its baseline schema at the next free major version instead of trying
    to replace the existing document.
    """
    schema = canonical_seed_schema(subject_type)
    for major in range(1, 10):
        try:
            existing = await resolver.get_schema(subject_type, major, 0)
        except DppNotFoundError:
            await resolver.publish_schema(subject_type, major, 0, schema)
            return DppSchemaVersion(subject_type=subject_type, major_version=major, minor_version=0)

        if _seed_schema_accepts_payload(subject_type, existing):
            return DppSchemaVersion(subject_type=subject_type, major_version=major, minor_version=0)

    raise RuntimeError(f"No compatible schema major version available for {subject_type}")


async def _ensure_battery_schema_with_cell_chemistry(
    resolver: ResolverClient,
    baseline: DppSchemaVersion,
) -> DppSchemaVersion:
    """Return a breaking battery schema version requiring ``cell_chemistry``."""
    for major in range(baseline.major_version + 1, 12):
        try:
            existing = await resolver.get_schema("battery", major, 0)
        except DppNotFoundError:
            schema = await resolver.get_schema("battery", baseline.major_version, baseline.minor_version)
            schema["properties"]["cell_chemistry"] = {"type": "string"}
            required = list(schema.get("required", []))
            if "cell_chemistry" not in required:
                required.append("cell_chemistry")
            schema["required"] = required
            await resolver.publish_schema("battery", major, 0, schema)
            return DppSchemaVersion(subject_type="battery", major_version=major, minor_version=0)

        if _battery_schema_requires_cell_chemistry(existing):
            return DppSchemaVersion(subject_type="battery", major_version=major, minor_version=0)

    raise RuntimeError("No battery schema major version available for the S2 breaking update")


def _seed_schema_accepts_payload(subject_type: str, schema: dict) -> bool:
    properties = schema.get("properties", {})
    if subject_type == "battery":
        return {"capacity_kwh", "chemistry"}.issubset(properties) and "cell_chemistry" not in schema.get("required", [])
    if subject_type == "pv_module":
        if schema.get("additionalProperties") is False and "dependencies" not in properties:
            return False
        return {"manufacturer", "model"}.issubset(properties)
    return False


def _battery_schema_requires_cell_chemistry(schema: dict) -> bool:
    return (
        "cell_chemistry" in schema.get("properties", {})
        and "cell_chemistry" in schema.get("required", [])
        and {"capacity_kwh", "chemistry"}.issubset(schema.get("properties", {}))
    )
