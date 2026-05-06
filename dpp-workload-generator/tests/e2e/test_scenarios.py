import pytest
import os
from pathlib import Path
from typer.testing import CliRunner
from workload.cli import app

runner = CliRunner()

def test_scenario_help():
    result = runner.invoke(app, ["scenario", "--help"])
    assert result.exit_code == 0
    assert "s1" in result.output
    assert "s2" in result.output

@pytest.mark.skipif(os.getenv("DOCKER_AVAILABLE") != "true", reason="Requires live federation")
def test_scenario_s1_full(tmp_path):
    result = runner.invoke(app, [
        "scenario", "s1", 
        "--output-dir", str(tmp_path),
        "--factory-url", os.getenv("FACTORY_URL", "http://localhost:8000")
    ])
    assert result.exit_code == 0
    
    # Verify report exists
    reports = list(tmp_path.glob("s1-*.md"))
    assert len(reports) == 1
    content = reports[0].read_text()
    assert "Outcome: PASSED" in content

@pytest.mark.skipif(os.getenv("DOCKER_AVAILABLE") != "true", reason="Requires live federation")
def test_scenario_s2_full(tmp_path):
    result = runner.invoke(app, [
        "scenario", "s2", 
        "--output-dir", str(tmp_path),
        "--factory-url", os.getenv("FACTORY_URL", "http://localhost:8000")
    ])
    assert result.exit_code == 0
    
    # Verify report exists
    reports = list(tmp_path.glob("s2-*.md"))
    assert len(reports) == 1
    content = reports[0].read_text()
    assert "Outcome: PASSED" in content
