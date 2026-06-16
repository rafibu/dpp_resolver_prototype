import structlog
from pathlib import Path
from typing import Optional

from .reporter import ScenarioReporter
from ..clients import ResolverClient, PlatformClient, IssueDppSpec, DppSchemaVersion, SchemaValidationError
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

        with reporter.step("Setup federation", "Federation discovered and reset"):
            fed = await fed_client.discover(factory_url)
            await fed_client.reset_all_platforms(factory_url)
            resolver_url = await fed_client.resolver_url()
            resolver = ResolverClient(resolver_url)

            await resolver.ensure_subject_type("battery")
            await resolver.publish_schema("battery", 1, 0, canonical_seed_schema("battery"))
            await resolver.ensure_subject_type("pv_module")
            await resolver.publish_schema("pv_module", 1, 0, canonical_seed_schema("pv_module"))

            reporter.record_observation("Federation ready, battery v1.0 and pv_module v1.0 published", True)

        try:
            if resolver is None:
                raise RuntimeError("Setup failed: resolver not available")

            platform_b = await fed_client.find_platform_for_subject_type("battery")
            with reporter.step("Issue battery DPP under schema 1.0", "battery DPP created with schema (battery, 1, 0)"):
                async with PlatformClient(platform_b) as client:
                    battery_spec = IssueDppSpec(
                        schema_version=DppSchemaVersion(subject_type="battery", major_version=1, minor_version=0),
                        dpp_payload=generate_seed_payload("battery", seed=seed)
                    )
                    battery_resp = await client.issue_dpp(battery_spec)
                    reporter.record_observation(f"Battery DPP issued: {battery_resp.dpp_id}", True)

            platform_a = await fed_client.find_platform_for_subject_type("pv_module")
            with reporter.step("Issue PV-module DPP with hard dep pinned to battery v1", "PV-module DPP created with hard ref"):
                if battery_resp is None:
                    raise RuntimeError("Battery DPP was not issued")
                async with PlatformClient(platform_a) as client:
                    pv_spec = IssueDppSpec(
                        schema_version=DppSchemaVersion(subject_type="pv_module", major_version=1, minor_version=0),
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
                # Build v2.0 on top of the actual v1.0 seed schema to keep existing fields valid.
                battery_schema_v2 = await resolver.get_schema("battery", 1, 0)
                battery_schema_v2["properties"]["cell_chemistry"] = {"type": "string"}
                battery_schema_v2["required"] = list(battery_schema_v2.get("required", [])) + ["cell_chemistry"]
                await resolver.publish_schema("battery", 2, 0, battery_schema_v2)
                reporter.record_observation("Battery schema 2.0 published with breaking change (required cell_chemistry)", True)

            with reporter.step("Verify battery schema 1.0 is still retrievable", "historical schemas remain accessible"):
                schema_v1 = await resolver.get_schema("battery", 1, 0)
                is_v1 = "cell_chemistry" not in schema_v1.get("required", [])
                reporter.record_observation("Schema 1.0 still available without cell_chemistry", is_v1)

            with reporter.step("Verify existing PV-module DPP remains valid", "PV-module's pinned battery still valid"):
                if pv_resp is None:
                    raise RuntimeError("PV-module DPP was not issued")
                async with PlatformClient(platform_a) as client:
                    await client.get_revision(pv_resp.dpp_id, pv_resp.version)
                    reporter.record_observation("Existing PV-module remains valid", True)

            with reporter.step("Issue a new battery DPP under schema 2.0", "new battery DPP satisfies 2.0 constraints"):
                async with PlatformClient(platform_b) as client:
                    payload_v2 = generate_seed_payload("battery", seed=seed + 2)
                    payload_v2["cell_chemistry"] = "Li-ion"
                    battery_v2_resp = await client.issue_dpp(IssueDppSpec(
                        schema_version=DppSchemaVersion(subject_type="battery", major_version=2, minor_version=0),
                        dpp_payload=payload_v2
                    ))
                    reporter.record_observation(f"New Battery DPP issued under 2.0: {battery_v2_resp.dpp_id}", True)

            with reporter.step("Try issuing a new battery DPP under 2.0 missing required field", "rejected by schema validation"):
                async with PlatformClient(platform_b) as client:
                    try:
                        await client.issue_dpp(IssueDppSpec(
                            schema_version=DppSchemaVersion(subject_type="battery", major_version=2, minor_version=0),
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
