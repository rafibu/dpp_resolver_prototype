import pytest
from unittest.mock import AsyncMock, patch
from workload.scenarios.fanout import generate_fanout
from workload.federation import FederationOverview, ResolverInfo, PlatformInfo, PlatformStatus
from workload.clients import DppResponse
from datetime import datetime

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
            ) for i in range(2)
        ]
    )

@pytest.mark.asyncio
async def test_generate_fanout_logic(mock_federation):
    with patch("workload.scenarios.fanout.ResolverClient") as MockResolver, \
         patch("workload.scenarios.fanout.PlatformClient") as MockPlatform:
        
        mock_resolver = MockResolver.return_value
        mock_resolver.ensure_subject_type = AsyncMock()
        mock_resolver.publish_schema = AsyncMock()
        
        mock_platform = MockPlatform.return_value
        mock_platform.__aenter__ = AsyncMock(return_value=mock_platform)
        mock_platform.__aexit__ = AsyncMock()
        
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

        result = await generate_fanout(mock_federation, fanout=5, seed=42)
        
        assert result.parent_dpp.schema_version.subject_type == "parent"
        assert len(result.children) == 5
        assert len(result.parent_dpp.dpp_payload["dependencies"]) == 5
        
        # Verify children are on platform-1 (since platform-0 is root)
        for child in result.children:
            assert result.platform_mapping[child.dpp_id] == "http://platform-1:8082"
        
        # Verify parent is on platform-0
        assert result.platform_mapping[result.parent_dpp.dpp_id] == "http://platform-0:8082"
