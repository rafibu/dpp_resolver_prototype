import structlog
from pydantic import BaseModel
from typing import List, Dict, Optional

from ..clients import PlatformClient, ResolverClient, IssueDppSpec, DppSchemaVersion, DppResponse
from ..federation import FederationOverview
from ..payloads import generate_valid_payload, generate_dpp_id, ReferenceSpec
from ..schemas.generator import generate_schema

logger = structlog.get_logger(__name__)

class FanoutResult(BaseModel):
    parent_dpp: DppResponse
    children: List[DppResponse]
    platform_mapping: Dict[str, str]

async def generate_fanout(federation: FederationOverview, fanout: int, root_platform: str | None = None, seed: int | None = None) -> FanoutResult:
    """
    Generate a parent DPP with N hard dependencies.

    Algorithm:
    1. Seed schemas for parent and child subject types
    2. Issue fanout distinct child DPPs distributed across platforms
    3. Issue parent DPP on root_platform with hard dependencies on all children
    """
    if not (1 <= fanout <= 20):
        raise ValueError("Fanout must be between 1 and 20")

    if not federation.resolver:
        raise RuntimeError("Federation has no resolver")

    resolver = ResolverClient(federation.resolver.external_url)
    platforms = federation.platforms
    if not platforms:
        raise RuntimeError("No platforms available in federation")

    # 1. Seed schemas
    await resolver.ensure_subject_type("parent")
    await resolver.publish_schema("parent", 1, 0, generate_schema("parent", with_dependencies=True))
    await resolver.ensure_subject_type("child")
    await resolver.publish_schema("child", 1, 0, generate_schema("child", with_dependencies=False))

    # Identify root platform
    if root_platform:
        root_platform_info = next((p for p in platforms if p.platform_id == root_platform), None)
        if not root_platform_info:
            logger.warning("root_platform_not_found", requested=root_platform)
            root_platform_info = platforms[0]
    else:
        root_platform_info = platforms[0]

    # 2. Issue children distributed across other platforms if possible
    other_platforms = [p for p in platforms if p.platform_id != root_platform_info.platform_id]
    if not other_platforms:
        other_platforms = platforms

    children = []
    platform_mapping = {}
    for i in range(1, fanout + 1):
        p_info = other_platforms[i % len(other_platforms)]
        async with PlatformClient(p_info) as client:
            child_seed = (seed + i) if seed is not None else None
            dpp_id = generate_dpp_id(p_info.issuer_id, "child", i)
            spec = IssueDppSpec(
                dpp_id=dpp_id,
                schema_version=DppSchemaVersion(subject_type="child", major_version=1, minor_version=0),
                dpp_payload=generate_valid_payload({}, seed=child_seed)
            )
            # Make the child routable before the parent hard-references it (I7).
            await resolver.ensure_platform_route(p_info, "child")

            logger.info("creating_fanout_child", index=i, total=fanout, platform=p_info.platform_id)
            resp = await client.issue_dpp(spec)
            children.append(resp)
            platform_mapping[resp.dpp_id] = p_info.external_url

    # 3. Issue parent DPP on root platform
    async with PlatformClient(root_platform_info) as client:
        dependencies = [
            ReferenceSpec(subject_type="child", dpp_id=c.dpp_id, version=c.version)
            for c in children
        ]
        dpp_id = generate_dpp_id(root_platform_info.issuer_id, "parent", 1)
        spec = IssueDppSpec(
            dpp_id=dpp_id,
            schema_version=DppSchemaVersion(subject_type="parent", major_version=1, minor_version=0),
            dpp_payload=generate_valid_payload({}, dependencies=dependencies, seed=seed)
        )
        await resolver.ensure_platform_route(root_platform_info, "parent")
        logger.info("creating_fanout_parent", platform=root_platform_info.platform_id)
        parent_resp = await client.issue_dpp(spec)
        platform_mapping[parent_resp.dpp_id] = root_platform_info.external_url

    return FanoutResult(
        parent_dpp=parent_resp,
        children=children,
        platform_mapping=platform_mapping
    )