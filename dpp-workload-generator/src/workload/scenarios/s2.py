import httpx
import structlog
from pathlib import Path
from typing import Optional
from ..federation import FederationClient
from ..clients import ResolverClient, PlatformClient, IssueDppSpec, DppSchemaVersion, SchemaValidationError
from ..payloads import generate_valid_payload, ReferenceSpec
from .reporter import ScenarioReporter

logger = structlog.get_logger(__name__)

async def run_s2(factory_url: str, seed: int, output_dir: Optional[Path] = None) -> bool:
    """Scenario S2: Independent Schema Evolution"""
    reporter = ScenarioReporter("s2", "Independent Schema Evolution", output_dir=output_dir)
    
    async with FederationClient() as fed_client:
        # Setup
        with reporter.step("Setup federation", "Federation discovered and reset"):
            fed = await fed_client.discover(factory_url)
            await fed_client.reset_all_platforms(factory_url)
            resolver_url = await fed_client.resolver_url()
            resolver = ResolverClient(resolver_url)
            
            # Seed battery 1.0 and pv_module 1.0
            from ..schemas.generator import generate_schema
            battery_schema_v1 = generate_schema("battery")
            pv_schema_v1 = generate_schema("pv_module", with_dependencies=True)
            
            await resolver.publish_schema("battery", 1, 0, battery_schema_v1)
            await resolver.publish_schema("pv_module", 1, 0, pv_schema_v1)
            
            reporter.record_observation("Federation ready, battery v1.0 and pv_module 1.0 published", True)

        # Step 4: Issue battery DPP under schema 1.0 on platform-b
        try:
            platform_b = await fed_client.find_platform_for_subject_type("battery")
            with reporter.step("Issue battery DPP under schema 1.0", "battery DPP created with schema (battery, 1, 0)"):
                async with PlatformClient(platform_b) as client:
                    battery_spec = IssueDppSpec(
                        schema_version=DppSchemaVersion(subject_type="battery", major_version=1, minor_version=0),
                        dpp_payload=generate_valid_payload({}, seed=seed)
                    )
                    battery_resp = await client.issue_dpp(battery_spec)
                    reporter.record_observation(f"Battery DPP issued: {battery_resp.dpp_id}", True)

            # Step 5: Issue PV-module DPP on platform-a with hard dep pinned to battery v1
            platform_a = await fed_client.find_platform_for_subject_type("pv_module")
            with reporter.step("Issue PV-module DPP with hard dep pinned to battery v1", "PV-module DPP created with hard ref"):
                async with PlatformClient(platform_a) as client:
                    pv_spec = IssueDppSpec(
                        schema_version=DppSchemaVersion(subject_type="pv_module", major_version=1, minor_version=0),
                        dpp_payload=generate_valid_payload({}, dependencies=[
                            ReferenceSpec(subject_type="battery", dpp_id=battery_resp.dpp_id, version=battery_resp.version)
                        ], seed=seed + 1)
                    )
                    pv_resp = await client.issue_dpp(pv_spec)
                    reporter.record_observation(f"PV-module DPP issued: {pv_resp.dpp_id}", True)

            # Step 6: Verify PV-module is valid (baseline)
            with reporter.step("Verify PV-module is valid (baseline)", "GET PV-module returns 200"):
                 async with PlatformClient(platform_a) as client:
                    await client.get_revision(pv_resp.dpp_id)
                    reporter.record_observation("PV-module valid against schema 1.0", True)

            # Step 7: Publish battery schema 2.0 (major update) via Resolver
            with reporter.step("Publish battery schema 2.0 (major update)", "schema published, marked as major"):
                battery_schema_v2 = generate_schema("battery")
                # Introduce a breaking change: new required field
                battery_schema_v2["properties"]["cell_chemistry"] = {"type": "string"}
                battery_schema_v2["required"] = battery_schema_v2.get("required", []) + ["cell_chemistry"]
                
                await resolver.publish_schema("battery", 2, 0, battery_schema_v2)
                reporter.record_observation("Battery schema 2.0 published with breaking change (required cell_chemistry)", True)

            # Step 8: Verify battery schema 1.0 is still retrievable
            with reporter.step("Verify battery schema 1.0 is still retrievable", "historical schemas remain accessible"):
                schema_v1 = await resolver.get_schema("battery", 1, 0)
                is_v1 = "cell_chemistry" not in schema_v1.get("required", [])
                reporter.record_observation("Schema 1.0 still available without cell_chemistry", is_v1)

            # Step 9: Verify existing PV-module DPP remains valid
            with reporter.step("Verify existing PV-module DPP remains valid", "PV-module's pinned battery still valid"):
                 async with PlatformClient(platform_a) as client:
                    await client.get_revision(pv_resp.dpp_id)
                    reporter.record_observation("Existing PV-module remains valid", True)

            # Step 10: Issue a new battery DPP under schema 2.0 on platform-b
            with reporter.step("Issue a new battery DPP under schema 2.0", "new battery DPP satisfies 2.0 constraints"):
                async with PlatformClient(platform_b) as client:
                    payload_v2 = generate_valid_payload({}, seed=seed + 2)
                    payload_v2["cell_chemistry"] = "Li-ion"
                    battery_spec_v2 = IssueDppSpec(
                        schema_version=DppSchemaVersion(subject_type="battery", major_version=2, minor_version=0),
                        dpp_payload=payload_v2
                    )
                    battery_v2_resp = await client.issue_dpp(battery_spec_v2)
                    reporter.record_observation(f"New Battery DPP issued under 2.0: {battery_v2_resp.dpp_id}", True)

            # Step 11: Try issuing a new battery DPP under 2.0 missing the new required field
            with reporter.step("Try issuing a new battery DPP under 2.0 missing required field", "rejected with 422"):
                async with PlatformClient(platform_b) as client:
                    payload_invalid = generate_valid_payload({}, seed=seed + 3)
                    # missing "cell_chemistry"
                    battery_spec_invalid = IssueDppSpec(
                        schema_version=DppSchemaVersion(subject_type="battery", major_version=2, minor_version=0),
                        dpp_payload=payload_invalid
                    )
                    try:
                        await client.issue_dpp(battery_spec_invalid)
                        reporter.record_observation("Unexpectedly accepted invalid payload", False)
                    except SchemaValidationError as e:
                        reporter.record_observation(f"Correctly rejected with 422: {str(e)[:100]}...", True)
        except Exception as e:
            logger.error("s2_step_failed", error=str(e))
            # The reporter handles exceptions inside step(), but if it happens outside, we catch it here
            pass

    report_path = reporter.finalize()
    logger.info("s2_complete", report_path=str(report_path))
    return reporter.result.outcome == "PASSED"
