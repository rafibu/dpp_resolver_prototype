import pytest
from pathlib import Path

from workload.scenarios.reporter import ScenarioReporter


def test_reporter_basic_flow(tmp_path):
    reporter = ScenarioReporter("s4", "Offline Interpretability Supplement", output_dir=tmp_path)
    
    with reporter.step("Cache dependencies", "All refs cached"):
        reporter.record_observation("2 references resolved", True, {"details": "none"})
        
    with reporter.step("Pause platform", "Unreachable"):
        reporter.record_observation("Connection refused", True)
        
    report_path = reporter.finalize()
    
    assert report_path.exists()
    content = report_path.read_text()
    assert "# Scenario S4: Offline Interpretability Supplement" in content
    assert "**Outcome:** PASSED" in content
    assert "### Step 1: Cache dependencies" in content
    assert "### Step 2: Pause platform" in content

def test_reporter_failure_aggregation(tmp_path):
    reporter = ScenarioReporter("s4", "Offline Interpretability Supplement", output_dir=tmp_path)
    
    with reporter.step("Step 1", "Success"):
        reporter.record_observation("Ok", True)
        
    with reporter.step("Step 2", "Failure expected"):
        reporter.record_observation("Something went wrong", False)
        
    report_path = reporter.finalize()
    
    content = report_path.read_text()
    assert "**Outcome:** FAILED" in content
    assert "Result: PASSED" in content
    assert "Result: FAILED" in content

def test_reporter_exception_handling(tmp_path):
    reporter = ScenarioReporter("s4", "Exception test", output_dir=tmp_path)
    
    with reporter.step("Step with exception", "Should handle it"):
        raise ValueError("Something broke")
        
    report_path = reporter.finalize()
    
    content = report_path.read_text()
    assert "**Outcome:** FAILED" in content
    assert "Exception: ValueError: Something broke" in content
    assert "Result: FAILED" in content
