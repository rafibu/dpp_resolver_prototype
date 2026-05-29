import structlog
from typing import Optional
from ..federation import FederationOverview
from ..clients import PlatformClient, ResolverClient, IssueDppSpec, ReviseDppSpec, DppSchemaVersion
from ..measurement import MeasurementRecorder, measure_operation
from ..schemas.generator import generate_schema
from ..payloads import generate_valid_payload, generate_dpp_id

logger = structlog.get_logger(__name__)

async def run_schema_evolution(
    federation: FederationOverview, 
    n_revisions: int, 
    update_kind: str, 
    recorder: MeasurementRecorder, 
    seed: Optional[int] = None
):
    """
    Measure the impact of schema evolution on DPP revision issuance.
    
    Algorithm:
    1. Seed schema v1.0
    2. Issue N revisions of a single DPP under v1.0 (recorded as baseline)
    3. Publish schema v1.1 (minor) or v2.0 (major) via Resolver
    4. Issue one revision under the new schema
    5. Capture latency of schema publication and issuance
    """
    if not (1 <= n_revisions <= 100):
        raise ValueError("n_revisions must be between 1 and 100")
    if update_kind not in ["minor", "major"]:
        raise ValueError("update_kind must be 'minor' or 'major'")

    if not federation.resolver:
        raise RuntimeError("Federation has no resolver")
    
    resolver = ResolverClient(federation.resolver.external_url)
    p_info = federation.platforms[0]
    subject_type = f"evolve_{update_kind}"
    
    # 1. Seed v1.0
    schema_v10 = generate_schema(subject_type)
    await resolver.ensure_subject_type(subject_type)
    await resolver.publish_schema(subject_type, 1, 0, schema_v10)
    
    # 2. Issue revisions under v1.0
    async with PlatformClient(p_info) as client:
        dpp_id = generate_dpp_id(p_info.issuer_id, subject_type, 1)
        
        # Initial issuance
        logger.info("schema_evolution_start", dpp_id=dpp_id, kind=update_kind)
        spec = IssueDppSpec(
            dpp_id=dpp_id,
            schema_version=DppSchemaVersion(subject_type=subject_type, major_version=1, minor_version=0),
            dpp_payload=generate_valid_payload(schema_v10, seed=seed)
        )
        await client.issue_dpp(spec)
        
        # N revisions
        for i in range(1, n_revisions):
            async with measure_operation(recorder, "issue_revision_baseline", n_revisions) as ctx:
                spec_r = ReviseDppSpec(
                    schema_version=DppSchemaVersion(subject_type=subject_type, major_version=1, minor_version=0),
                    dpp_payload=generate_valid_payload(schema_v10, seed=seed + i if seed else None)
                )
                await client.revise_dpp(dpp_id, spec_r)

        # 3. Publish schema evolution
        major, minor = (2, 0) if update_kind == "major" else (1, 1)
        schema_new = generate_schema(subject_type)
        if update_kind == "major":
            # Add a mandatory field for major update to ensure strictness
            schema_new["properties"]["major_field"] = {"type": "string"}
            schema_new["required"].append("major_field")
            
        async with measure_operation(recorder, f"publish_schema_{update_kind}", n_revisions) as ctx:
            await resolver.publish_schema(subject_type, major, minor, schema_new)
            
        # 4. Issue under new schema
        payload_new = generate_valid_payload(schema_new, seed=seed + 999 if seed else None)
        if update_kind == "major":
            payload_new["major_field"] = "breaking change"
            
        async with measure_operation(recorder, f"issue_revision_evolved", n_revisions) as ctx:
            spec_new = ReviseDppSpec(
                schema_version=DppSchemaVersion(subject_type=subject_type, major_version=major, minor_version=minor),
                dpp_payload=payload_new
            )
            await client.revise_dpp(dpp_id, spec_new)
            
    logger.info("schema_evolution_complete", dpp_id=dpp_id)
