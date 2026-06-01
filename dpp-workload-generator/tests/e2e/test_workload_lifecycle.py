import os
import subprocess
from pathlib import Path

import httpx
import pandas as pd
import pytest

# Skip if factory is not reachable
FACTORY_URL = os.environ.get("FACTORY_URL", "http://localhost:8000")

def is_factory_up():
    try:
        resp = httpx.get(f"{FACTORY_URL}/health", timeout=1.0)
        return resp.status_code == 200
    except Exception:
        return False

@pytest.fixture(scope="module")
def workload_bin():
    # Try to find the workload executable in the current venv
    # Path is relative to where pytest is run (project root or workload-generator)
    paths = [
        Path(".venv/Scripts/workload.exe"),
        Path("../.venv/Scripts/workload.exe"),
        Path("workload-generator/.venv/Scripts/workload.exe")
    ]
    for p in paths:
        if p.exists():
            return str(p.absolute())
    return "workload" # Fallback to PATH

def run_cmd(workload_bin, args):
    # --factory-url is a per-subcommand option, not a global flag
    cmd = [workload_bin] + args + ["--factory-url", FACTORY_URL]
    return subprocess.run(cmd, capture_output=True, text=True)

@pytest.mark.skipif(not is_factory_up(), reason="Factory not reachable")
class TestWorkloadLifecycle:
    def test_pv_scenario(self, workload_bin):
        result = run_cmd(workload_bin, ["pv-scenario", "--seed", "123"])
        assert result.returncode == 0
        assert "Created PV scenario" in result.stdout
        assert "PV Module:" in result.stdout

    def test_generate_depth(self, workload_bin):
        result = run_cmd(workload_bin, ["generate-depth", "--depth", "5", "--seed", "42"])
        assert result.returncode == 0
        assert "Created depth chain (depth=5)" in result.stdout
        assert "link_5" in result.stdout

    def test_generate_fanout(self, workload_bin):
        result = run_cmd(workload_bin, ["generate-fanout", "--fanout", "10", "--seed", "42"])
        assert result.returncode == 0
        assert "Created fan-out (fanout=10)" in result.stdout
        assert "Parent DPP:" in result.stdout

    def test_measure_depth(self, workload_bin, tmp_path):
        result = run_cmd(workload_bin, [
            "measure", "--workload", "depth", "--range", "1-3", 
            "--runs", "2", "--warmup-runs", "1", 
            "--output", str(tmp_path)
        ])
        assert result.returncode == 0
        
        csv_files = list(tmp_path.glob("depth-*.csv"))
        assert len(csv_files) == 1
        df = pd.read_csv(csv_files[0])
        # 3 param values * (2 runs + 1 warmup) = 9 rows
        assert len(df) == 9
        assert df[df["warmup"] == False].shape[0] == 6

    def test_measure_fanout(self, workload_bin, tmp_path):
        result = run_cmd(workload_bin, [
            "measure", "--workload", "fanout", "--range", "1-5", 
            "--runs", "2", "--output", str(tmp_path)
        ])
        assert result.returncode == 0
        assert len(list(tmp_path.glob("fanout-*.csv"))) == 1

    def test_schema_evolution(self, workload_bin, tmp_path):
        result = run_cmd(workload_bin, [
            "schema-evolution", "--revisions", "5", "--update-kind", "minor", 
            "--output", str(tmp_path)
        ])
        assert result.returncode == 0
        csv_files = list(tmp_path.glob("schema-evolution-minor-*.csv"))
        assert len(csv_files) == 1
        df = pd.read_csv(csv_files[0])
        # 4 baseline + 1 evolved schema + 1 evolved revision = 6 rows
        assert len(df) >= 6
