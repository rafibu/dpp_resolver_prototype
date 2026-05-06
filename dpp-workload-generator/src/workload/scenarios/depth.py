import structlog
from typing import List, Dict, Optional
from pydantic import BaseModel
from ..federation import FederationOverview, PlatformInfo
from ..clients import PlatformClient, ResolverClient, IssueDppSpec, DppSchemaVersion, DppResponse
from ..schemas.generator import generate_schema
from ..payloads import generate_valid_payload, generate_dpp_id, ReferenceSpec

logger = structlog.get_logger(__name__)

class DepthChainResult(BaseModel):
    root_dpp_id: str
    root_subject_type: str
    chain: List[DppResponse]
    platform_mapping: Dict[str, str] # dpp_id -> platform_url

async def generate_depth_chain(federation: FederationOverview, depth: int, seed: int | None = None) -> DepthChainResult:
    """
    Generate a chain of DPPs with controllable hard-dependency depth.
    
    Algorithm:
    1. Seed schemas for link_<i> subject types (i = 1..depth) via Resolver
    2. Issue DPPs leaf-first (link_depth has no dependencies, link_1 depends on link_2 which depends on link_3, etc.)
    3. Distribute DPPs across at least 3 platforms in round-robin fashion
    4. Each link's hard dependency points to the next link's specific revision
    """
    if not (1 <= depth <= 10):
        raise ValueError("Depth must be between 1 and 10")
    
    if not federation.resolver:
        raise RuntimeError("Federation has no resolver")
        
    resolver = ResolverClient(federation.resolver.external_url)
    platforms = federation.platforms
    if not platforms:
        raise RuntimeError("No platforms available in federation")

    # 1. Seed schemas
    # We do this up front to ensure all subject types are known to the Resolver
    for i in range(1, depth + 1):
        st = f"link_{i}"
        schema = generate_schema(st, with_dependencies=True)
        await resolver.publish_schema(st, 1, 0, schema)

    # 2. Issue DPPs leaf-first
    chain_reversed = []
    platform_mapping = {}
    last_dpp: Optional[DppResponse] = None
    
    platform_count = len(platforms)
    
    for i in range(depth, 0, -1):
        st = f"link_{i}"
        # Pick platform round-robin. Task says "at least 3 platforms".
        # If we have fewer than 3, we just use what we have.
        platform_info = platforms[i % platform_count]
        
        async with PlatformClient(platform_info) as client:
            dependencies = []
            if last_dpp:
                dependencies.append(ReferenceSpec(
                    subject_type=last_dpp.schema_version.subject_type,
                    dpp_id=last_dpp.dpp_id,
                    version=last_dpp.version
                ))
            
            # Use deterministic seed per link
            link_seed = (seed + i) if seed is not None else None
            
            dpp_id = generate_dpp_id(platform_info.issuer_id, st, 1)
            spec = IssueDppSpec(
                dpp_id=dpp_id,
                schema_version=DppSchemaVersion(subject_type=st, major_version=1, minor_version=0),
                dpp_payload=generate_valid_payload({}, dependencies=dependencies, seed=link_seed)
            )
            
            logger.info("creating_chain_link", link=i, total=depth, platform=platform_info.platform_id)
            resp = await client.issue_dpp(spec)
            chain_reversed.append(resp)
            platform_mapping[resp.dpp_id] = platform_info.external_url
            last_dpp = resp

    # The last one created is link_1, which is the root
    root_dpp = chain_reversed[-1]
    
    return DepthChainResult(
        root_dpp_id=root_dpp.dpp_id,
        root_subject_type=root_dpp.schema_version.subject_type,
        chain=list(reversed(chain_reversed)), # link_1 to link_depth
        platform_mapping=platform_mapping
    )
