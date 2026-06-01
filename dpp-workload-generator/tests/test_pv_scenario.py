from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from workload.clients import DppResponse
from workload.federation import FederationOverview, ResolverInfo, PlatformInfo, PlatformStatus
from workload.scenarios.pv import generate_pv_scenario


@pytest.fixture
def mock_federation():
    return FederationOverview(
        resolver=ResolverInfo(external_url="http://resolver:8081", status=PlatformStatus.RUNNING),
        platforms=[
            PlatformInfo(
                platform_id="platform-pv",
                stack="java",
                issuer_id="issuerPV",
                subject_types=["pv_module"],
                external_url="http://platform-pv:8082",
                status=PlatformStatus.RUNNING,
                created_at=datetime.now()
            ),
            PlatformInfo(
                platform_id="platform-ba",
                stack="java",
                issuer_id="issuerBA",
                subject_types=["battery"],
                external_url="http://platform-ba:8082",
                status=PlatformStatus.RUNNING,
                created_at=datetime.now()
            ),
            PlatformInfo(
                platform_id="platform-in",
                stack="java",
                issuer_id="issuerIN",
                subject_types=["inverter"],
                external_url="http://platform-in:8082",
                status=PlatformStatus.RUNNING,
                created_at=datetime.now()
            )
        ]
    )

@pytest.mark.asyncio
async def test_generate_pv_scenario_logic(mock_federation):
    with patch("workload.scenarios.pv.ResolverClient") as MockResolver, \
         patch("workload.scenarios.pv.PlatformClient") as MockPlatform:
        
        mock_resolver = MockResolver.return_value
        mock_resolver.ensure_subject_type = AsyncMock()
        mock_resolver.publish_schema = AsyncMock()
        mock_resolver.ensure_platform_route = AsyncMock()
        
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

        result = await generate_pv_scenario(mock_federation, seed=42)
        
        assert result.pv_module.schema_version.subject_type == "pv_module"
        assert result.battery.schema_version.subject_type == "battery"
        assert result.inverter.schema_version.subject_type == "inverter"
        
        # Hard refs use a flat dependencies array (components.$ref would confuse the Java validator)
        deps = result.pv_module.dpp_payload["dependencies"]
        assert any(d["$ref"] == f"battery/{result.battery.dpp_id}" and d["version"] == result.battery.version
                   for d in deps)
        assert any(d["$ref"] == f"inverter/{result.inverter.dpp_id}" and d["version"] == result.inverter.version
                   for d in deps)
        
        # Verify platform mapping
        assert result.platform_mapping[result.pv_module.dpp_id] == "http://platform-pv:8082"
        assert result.platform_mapping[result.battery.dpp_id] == "http://platform-ba:8082"
        assert result.platform_mapping[result.inverter.dpp_id] == "http://platform-in:8082"
