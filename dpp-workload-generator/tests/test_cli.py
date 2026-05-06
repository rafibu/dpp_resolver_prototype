import pytest
from typer.testing import CliRunner
from workload.cli import app
from unittest.mock import AsyncMock, patch, MagicMock

runner = CliRunner()

def test_measure_help():
    result = runner.invoke(app, ["measure", "--help"])
    assert result.exit_code == 0
    assert "Run a parameterized measurement" in result.output

@pytest.mark.asyncio
async def test_run_measure_logic():
    # We test the internal _run_measure function to avoid issues with typer.run and asyncio
    from workload.cli import _run_measure
    
    with patch("workload.cli.FederationClient") as MockFed, \
         patch("workload.cli.MeasurementRecorder") as MockRecorder, \
         patch("workload.cli.generate_depth_chain") as MockDepth, \
         patch("workload.cli.ResolverClient") as MockResolver:
        
        mock_fed_client = MockFed.return_value
        mock_fed_client.__aenter__.return_value = mock_fed_client
        mock_fed_client.discover = AsyncMock()
        mock_fed_client.reset_all_platforms = AsyncMock()
        
        mock_recorder = MockRecorder.return_value
        mock_recorder.end_run.return_value = MagicMock()
        
        mock_depth_result = MagicMock()
        mock_depth_result.root_subject_type = "st"
        mock_depth_result.root_dpp_id = "id"
        MockDepth.return_value = mock_depth_result
        
        mock_resolver = MockResolver.return_value
        mock_resolver.resolve = AsyncMock()
        
        # Mock _resolve_recursive to not do real network calls
        with patch("workload.cli._resolve_recursive", new_callable=AsyncMock) as mock_resolve_recursive:
            await _run_measure(
                workload="depth",
                range_str="1-2",
                runs=1,
                warmup_runs=0,
                output=None,
                seed=42,
                factory_url="http://factory"
            )
            
            assert mock_fed_client.discover.called
            assert mock_fed_client.reset_all_platforms.call_count == 2 # 2 param values * 1 run
            assert mock_resolve_recursive.call_count == 2
            assert mock_recorder.end_run.called

def test_generate_depth_help():
    result = runner.invoke(app, ["generate-depth", "--help"])
    assert result.exit_code == 0
    assert "Generate a depth chain fixture" in result.output

@pytest.mark.asyncio
async def test_run_generate_depth_logic():
    from workload.cli import _run_generate_depth
    with patch("workload.cli.FederationClient") as MockFed, \
         patch("workload.cli.generate_depth_chain") as MockDepth:
        
        mock_fed_client = MockFed.return_value
        mock_fed_client.__aenter__.return_value = mock_fed_client
        mock_fed_client.discover = AsyncMock()
        
        mock_result = MagicMock()
        mock_result.root_subject_type = "st"
        mock_result.root_dpp_id = "id"
        mock_result.chain = []
        MockDepth.return_value = mock_result
        
        await _run_generate_depth(depth=3, seed=42, factory_url="http://factory")
        
        assert mock_fed_client.discover.called
        assert MockDepth.called
