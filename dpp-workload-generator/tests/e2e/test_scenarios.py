import os
import pytest
from typer.testing import CliRunner

from workload.cli import app

runner = CliRunner()


def test_scenario_help():
    result = runner.invoke(app, ["scenario", "--help"])
    assert result.exit_code == 0
    assert "s1" in result.output
    assert "s2" in result.output
    assert "s3" in result.output
    assert "s4" in result.output


def _run_scenario(scenario_id: str, tmp_path) -> str:
    result = runner.invoke(app, [
        "scenario", scenario_id,
        "--output-dir", str(tmp_path),
        "--factory-url", os.getenv("FACTORY_URL", "http://localhost:8000")
    ])
    reports = list(tmp_path.glob(f"{scenario_id}-*.md"))
    report_content = reports[0].read_text() if reports else "(no report written)"
    assert result.exit_code == 0, (
        f"Scenario {scenario_id.upper()} exited with code {result.exit_code}.\n"
        f"CLI output:\n{result.output}\n"
        f"Exception: {result.exception}\n"
        f"Report:\n{report_content}"
    )
    assert "**Outcome:** PASSED" in report_content, (
        f"Scenario {scenario_id.upper()} ran but did not PASS.\nReport:\n{report_content}"
    )
    return report_content


@pytest.mark.skipif(os.getenv("DOCKER_AVAILABLE") != "true", reason="Requires live federation")
def test_scenario_s1_full(tmp_path):
    _run_scenario("s1", tmp_path)


@pytest.mark.skipif(os.getenv("DOCKER_AVAILABLE") != "true", reason="Requires live federation")
def test_scenario_s4_full(tmp_path):
    _run_scenario("s4", tmp_path)


@pytest.mark.skipif(os.getenv("DOCKER_AVAILABLE") != "true", reason="Requires live federation")
def test_scenario_s2_full(tmp_path):
    _run_scenario("s2", tmp_path)


@pytest.mark.skipif(os.getenv("DOCKER_AVAILABLE") != "true", reason="Requires live federation")
def test_scenario_s3_full(tmp_path):
    _run_scenario("s3", tmp_path)
