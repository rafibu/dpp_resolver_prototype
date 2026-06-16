"""
Scenario S3: Schema-Level Cycle Rejection

Setup: two subject types A and B. Schema A declares a hard-reference target of type B.
Schema B then attempts to declare a hard-reference target of type A.

Expected outcome: the Resolver rejects the second publication because adding edge B -> A
would close the cycle A -> B -> A, violating Invariant I6 (schema-graph acyclicity,
Definition 13). Cycle prevention operates at schema-publication time, before any DPP
revision of either type is issued.
"""
import structlog
from pathlib import Path
from typing import Optional

from .reporter import ScenarioReporter
from ..clients import ResolverClient, SchemaValidationError
from ..federation import FederationClient
from ..schemas.generator import generate_schema

logger = structlog.get_logger(__name__)

_TYPE_A = "s3_cycle_a"
_TYPE_B = "s3_cycle_b"


async def run_s3(factory_url: str, seed: int, output_dir: Optional[Path] = None) -> bool:
    """Scenario S3: Schema-Level Cycle Rejection."""
    reporter = ScenarioReporter("s3", "Schema-Level Cycle Rejection", output_dir=output_dir)

    async with FederationClient() as fed_client:
        resolver = None

        with reporter.step("Setup federation", "Federation discovered and reset"):
            fed = await fed_client.discover(factory_url)
            await fed_client.reset_all_platforms(factory_url)
            resolver_url = await fed_client.resolver_url()
            resolver = ResolverClient(resolver_url)
            await resolver.ensure_subject_type(_TYPE_A)
            await resolver.ensure_subject_type(_TYPE_B)
            reporter.record_observation("Subject types registered, resolver ready", True)

        if resolver is None:
            reporter.finalize()
            return False

        # Step 1: Publish schema A declaring a hard reference to type B.
        # The Resolver extracts the x-dpp-reference annotation and adds edge A -> B
        # to the schema dependency graph (Definition 13). No cycle exists yet.
        with reporter.step(
            f"Publish schema {_TYPE_A} with hard-reference target {_TYPE_B}",
            "Schema accepted, edge A -> B added to schema dependency graph"
        ):
            schema_a = generate_schema(_TYPE_A, hard_reference_targets=[_TYPE_B])
            await resolver.publish_schema(_TYPE_A, 1, 0, schema_a)
            reporter.record_observation(
                f"Schema {_TYPE_A} 1.0 accepted, edge {_TYPE_A} -> {_TYPE_B} in G_S", True
            )

        # Step 2: Attempt to publish schema B declaring a hard reference to type A.
        # This would add edge B -> A, closing the cycle A -> B -> A.
        # Precondition P4 of publishSchema must reject this.
        with reporter.step(
            f"Attempt to publish schema {_TYPE_B} with hard-reference target {_TYPE_A}",
            f"Rejected with 422: adding B -> A would close cycle A -> B -> A (I6 preserved)"
        ):
            schema_b = generate_schema(_TYPE_B, hard_reference_targets=[_TYPE_A])
            try:
                await resolver.publish_schema(_TYPE_B, 1, 0, schema_b)
                reporter.record_observation(
                    f"Unexpectedly accepted schema {_TYPE_B} with cyclic dependency", False
                )
            except SchemaValidationError as exc:
                reporter.record_observation(
                    f"Correctly rejected with 422 (schema_cycle_detected): {str(exc)[:120]}", True
                )

        # Step 3: Confirm schema A is still intact and schema B was not stored.
        with reporter.step(
            f"Confirm {_TYPE_A} 1.0 is retrievable and {_TYPE_B} 1.0 is absent",
            f"{_TYPE_A} returns 200, {_TYPE_B} returns 404"
        ):
            try:
                await resolver.get_schema(_TYPE_A, 1, 0)
                a_present = True
            except Exception:
                a_present = False

            try:
                await resolver.get_schema(_TYPE_B, 1, 0)
                b_present = True
            except Exception:
                b_present = False

            success = a_present and not b_present
            reporter.record_observation(
                f"{_TYPE_A} retrievable: {a_present}, {_TYPE_B} absent: {not b_present}", success
            )

    report_path = reporter.finalize()
    logger.info("s3_complete", report_path=str(report_path))
    return reporter.result.outcome == "PASSED"
