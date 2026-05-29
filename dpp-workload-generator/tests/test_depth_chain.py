import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from workload.clients import DppResponse, DppSchemaVersion
from workload.federation import FederationOverview, ResolverInfo, PlatformInfo, PlatformStatus
from workload.scenarios.depth import generate_depth_chain


@pytest.fixture
def mock_federation():
    return FederationOverview(
        resolver=ResolverInfo(external_url="http://resolver:8081", status=PlatformStatus.RUNNING),
        platforms=[
            PlatformInfo(
                platform_id=f"platform-{i}",
                stack="java",
                issuer_id=f"issuer{i}",
                subject_types=[],
                external_url=f"http://platform-{i}:8082",
                status=PlatformStatus.RUNNING,
                created_at=datetime.now()
            ) for i in range(3)
        ]
    )

@pytest.mark.asyncio
async def test_generate_depth_chain_logic(mock_federation):
    # Mock ResolverClient and PlatformClient
    with patch("workload.scenarios.depth.ResolverClient") as MockResolver, \
         patch("workload.scenarios.depth.PlatformClient") as MockPlatform:
        
        mock_resolver = MockResolver.return_value
        mock_resolver.ensure_subject_type = AsyncMock()
        mock_resolver.publish_schema = AsyncMock()
        
        mock_platform = MockPlatform.return_value
        mock_platform.__aenter__ = AsyncMock(return_value=mock_platform)
        mock_platform.__aexit__ = AsyncMock()
        
        # Mock issue_dpp to return a DppResponse
        def side_effect(spec):
            return DppResponse(
                dpp_id=spec.dpp_id or "auto-id",
                version=1,
                schema_version=spec.schema_version,
                dpp_payload=spec.dpp_payload,
                payload_hash="hash",
                created_at=datetime.now()
            )
        mock_platform.issue_dpp = AsyncMock(side_effect=side_effect)

        result = await generate_depth_chain(mock_federation, depth=3, seed=42)
        
        assert result.root_subject_type == "link_1"
        assert len(result.chain) == 3
        assert result.chain[0].schema_version.subject_type == "link_1"
        assert result.chain[1].schema_version.subject_type == "link_2"
        assert result.chain[2].schema_version.subject_type == "link_3"
        
        # Verify link_1 depends on link_2
        link1_payload = result.chain[0].dpp_payload
        assert link1_payload["dependencies"][0]["$ref"] == "link_2/" + result.chain[1].dpp_id
        
        # Verify round-robin (3 links, 3 platforms)
        assert len(set(result.platform_mapping.values())) == 3
        
        # Verify subject type registration and schema seeding (one call per link)
        assert mock_resolver.ensure_subject_type.call_count == 3
        assert mock_resolver.publish_schema.call_count == 3
