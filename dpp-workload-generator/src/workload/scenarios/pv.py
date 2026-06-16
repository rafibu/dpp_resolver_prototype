import structlog
from pydantic import BaseModel
from typing import List, Dict, Optional

from ..clients import (
    DppNotFoundError,
    PlatformClient,
    ResolverClient,
    IssueDppSpec,
    DppSchemaVersion,
    DppResponse,
)
from ..federation import FederationOverview
from ..payloads import generate_seed_payload, generate_dpp_id, ReferenceSpec
from ..seed_schemas import canonical_seed_schema

logger = structlog.get_logger(__name__)

class PvScenarioResult(BaseModel):
    pv_module: DppResponse
    battery: DppResponse
    inverter: DppResponse
    platform_mapping: Dict[str, str]

async def generate_pv_scenario(federation: FederationOverview, seed: int | None = None) -> PvScenarioResult:
    """
    Materialize the PV/battery/inverter scenario from the paper's running example.
    
    Algorithm:
    1. Verify the federation has platforms supporting pv_module, battery, inverter
    2. Seed all three schemas at version 1.0 via Resolver
    3. Issue battery DPP on the platform handling battery
    4. Issue inverter DPP on the platform handling inverter
    5. Issue PV-module DPP on the platform handling pv_module, with hard dependencies on the battery and inverter
    """
    if not federation.resolver:
        raise RuntimeError("Federation has no resolver")
    
    resolver = ResolverClient(federation.resolver.external_url)
    
    # 1. Verify support
    platforms = federation.platforms
    def find_p(st):
        for p in platforms:
            if st in p.subject_types:
                return p
        return None

    p_pv = find_p("pv_module")
    p_ba = find_p("battery")
    p_in = find_p("inverter")
    
    if not all([p_pv, p_ba, p_in]):
        missing = [st for st, p in [("pv_module", p_pv), ("battery", p_ba), ("inverter", p_in)] if not p]
        logger.warning("missing_subject_type_support", missing=missing)
        # If specific platforms are missing, we use available platforms as fallback
        # but the task implies they should be there.
        if not platforms:
            raise RuntimeError("No platforms available")
        p_pv = p_pv or platforms[0]
        p_ba = p_ba or platforms[1 % len(platforms)]
        p_in = p_in or platforms[2 % len(platforms)]

    # 2. Seed schemas. If an earlier run published an incompatible immutable
    # schema at 1.0, use the next free major version for the canonical schema.
    schema_versions: dict[str, DppSchemaVersion] = {}
    for st in ["pv_module", "battery", "inverter"]:
        await resolver.ensure_subject_type(st)
        schema_versions[st] = await _ensure_compatible_seed_schema(resolver, st)

    # 3. Issue battery — payload conforms to the seed schema (required: capacity_kwh, chemistry)
    async with PlatformClient(p_ba) as client:
        dpp_id = generate_dpp_id(p_ba.issuer_id, "battery", 1)
        spec = IssueDppSpec(
            dpp_id=dpp_id,
            schema_version=schema_versions["battery"],
            dpp_payload=generate_seed_payload("battery", seed=seed + 1 if seed else None)
        )
        await resolver.ensure_platform_route(p_ba, "battery")
        logger.info("creating_pv_scenario_battery", platform=p_ba.platform_id)
        battery_resp = await client.issue_dpp(spec)

    # 4. Issue inverter — payload conforms to the seed schema (required: max_ac_power_watts)
    async with PlatformClient(p_in) as client:
        dpp_id = generate_dpp_id(p_in.issuer_id, "inverter", 1)
        spec = IssueDppSpec(
            dpp_id=dpp_id,
            schema_version=schema_versions["inverter"],
            dpp_payload=generate_seed_payload("inverter", seed=seed + 2 if seed else None)
        )
        await resolver.ensure_platform_route(p_in, "inverter")
        logger.info("creating_pv_scenario_inverter", platform=p_in.platform_id)
        inverter_resp = await client.issue_dpp(spec)

    # 5. Issue PV-module — references go in components.<subject_type> as declared by
    # x-dpp-reference annotations in the seed schema (not a dependencies array)
    async with PlatformClient(p_pv) as client:
        dpp_id = generate_dpp_id(p_pv.issuer_id, "pv_module", 1)
        spec = IssueDppSpec(
            dpp_id=dpp_id,
            schema_version=schema_versions["pv_module"],
            dpp_payload=generate_seed_payload(
                "pv_module",
                seed=seed,
                hard_refs={
                    "battery": ReferenceSpec(subject_type="battery", dpp_id=battery_resp.dpp_id,
                                             version=battery_resp.version),
                    "inverter": ReferenceSpec(subject_type="inverter", dpp_id=inverter_resp.dpp_id,
                                              version=inverter_resp.version)
                }
            )
        )
        await resolver.ensure_platform_route(p_pv, "pv_module")
        logger.info("creating_pv_scenario_root", platform=p_pv.platform_id)
        pv_resp = await client.issue_dpp(spec)

    return PvScenarioResult(
        pv_module=pv_resp,
        battery=battery_resp,
        inverter=inverter_resp,
        platform_mapping={
            pv_resp.dpp_id: p_pv.external_url,
            battery_resp.dpp_id: p_ba.external_url,
            inverter_resp.dpp_id: p_in.external_url
        }
    )


async def _ensure_compatible_seed_schema(
    resolver: ResolverClient,
    subject_type: str,
) -> DppSchemaVersion:
    """Return a canonical payload-compatible schema version for a seed subject.

    Resolver schemas are immutable. Some older workload runs published generic
    schemas as ``battery/1.0`` or ``inverter/1.0`` even though the PV scenario
    issues canonical battery/inverter payloads. Because replacing those fields
    is a major schema change, recovery publishes the canonical Factory-style
    schema at the next free major version and issues against that version.
    """
    schema = canonical_seed_schema(subject_type)
    for major in range(1, 10):
        try:
            existing = await resolver.get_schema(subject_type, major, 0)
        except DppNotFoundError:
            await resolver.publish_schema(subject_type, major, 0, schema)
            return DppSchemaVersion(
                subject_type=subject_type,
                major_version=major,
                minor_version=0,
            )

        if _seed_schema_accepts_payload(subject_type, existing):
            return DppSchemaVersion(
                subject_type=subject_type,
                major_version=major,
                minor_version=0,
            )

    raise RuntimeError(f"No compatible schema major version available for {subject_type}")


def _seed_schema_accepts_payload(subject_type: str, schema: dict) -> bool:
    properties = schema.get("properties", {})
    if subject_type == "battery":
        return {"capacity_kwh", "chemistry"}.issubset(properties)
    if subject_type == "inverter":
        return "max_ac_power_watts" in properties
    if subject_type == "pv_module":
        if schema.get("additionalProperties") is False and "dependencies" not in properties:
            return False
        return {"manufacturer", "model"}.issubset(properties)
    return False
