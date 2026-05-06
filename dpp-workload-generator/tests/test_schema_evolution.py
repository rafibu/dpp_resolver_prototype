import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from workload.scenarios.schema_evolution import run_schema_evolution
from workload.federation import FederationOverview, ResolverInfo, PlatformInfo, PlatformStatus
from workload.clients import DppResponse
from datetime import datetime

@pytest.fixture
def mock_federation():
    return FederationOverview(
        resolver=ResolverInfo(external_url="http://resolver:8081", status=PlatformStatus.RUNNING),
        platforms=[
            PlatformInfo(
                platform_id="p1", stack="java", issuer_id="i1", subject_types=[],
                external_url="http://p1", status=PlatformStatus.RUNNING, created_at=datetime.now()
            )
        ]
    )

@pytest.mark.asyncio
async def test_run_schema_evolution_minor(mock_federation):
    with patch("workload.scenarios.schema_evolution.ResolverClient") as MockResolver, \
         patch("workload.scenarios.schema_evolution.PlatformClient") as MockPlatform:
        
        mock_resolver = MockResolver.return_value
        mock_resolver.publish_schema = AsyncMock()
        
        mock_platform = MockPlatform.return_value
        mock_platform.__aenter__ = AsyncMock(return_value=mock_platform)
        mock_platform.__aexit__ = AsyncMock()
        
        def side_effect(arg1, arg2=None, *args, **kwargs):
            # For issue_dpp(spec), arg1 is spec.
            # For revise_dpp(dpp_id, spec), arg1 is dpp_id, arg2 is spec.
            spec = arg2 if arg2 is not None else arg1
            return DppResponse(
                dpp_id=getattr(spec, "dpp_id", None) or (arg1 if isinstance(arg1, str) else "id"), 
                version=1, 
                schema_version=spec.schema_version, 
                dpp_payload=spec.dpp_payload, 
                payload_hash="h", 
                created_at=datetime.now()
            )
        mock_platform.issue_dpp = AsyncMock(side_effect=side_effect)
        mock_platform.revise_dpp = AsyncMock(side_effect=side_effect)
        
        from workload.measurement import MeasurementRecorder
        recorder = MeasurementRecorder(output_dir="output")
        
        await run_schema_evolution(mock_federation, n_revisions=2, update_kind="minor", recorder=recorder)
        
        # 1. Publish v1.0
        # 2. Issue initial
        # 3. Issue 1 revision (baseline)
        # 4. Publish v1.1
        # 5. Issue 1 revision (evolved)
        
        assert mock_resolver.publish_schema.call_count == 2 # v1.0 and v1.1
        assert mock_platform.issue_dpp.call_count == 1
        assert mock_platform.revise_dpp.call_count == 2 # 1 baseline + 1 evolved
