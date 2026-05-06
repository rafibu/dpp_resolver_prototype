import pytest
import csv
import os
from pathlib import Path
from workload.measurement import MeasurementRecorder, measure_operation

@pytest.fixture
def temp_output(tmp_path):
    return tmp_path

@pytest.mark.asyncio
async def test_measurement_recorder_csv(temp_output):
    recorder = MeasurementRecorder(output_dir=str(temp_output))
    recorder.start_run("run-1", "test-workload")
    
    async with measure_operation(recorder, "op1", 10) as ctx:
        ctx.bytes_payload = 100
        # some work
        pass
        
    csv_path = recorder.end_run()
    
    assert csv_path.exists()
    assert csv_path.name.startswith("test-workload-")
    
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-1"
        assert rows[0]["operation"] == "op1"
        assert rows[0]["parameter_value"] == "10"
        assert rows[0]["bytes_payload"] == "100"
        assert float(rows[0]["latency_ms"]) >= 0

@pytest.mark.asyncio
async def test_measurement_error_capture(temp_output):
    recorder = MeasurementRecorder(output_dir=str(temp_output))
    recorder.start_run("run-2", "error-workload")
    
    with pytest.raises(RuntimeError, match="Failure"):
        async with measure_operation(recorder, "op_fail", 5):
            raise RuntimeError("Failure")
            
    csv_path = recorder.end_run()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert rows[0]["success"] == "False"
        assert "Failure" in rows[0]["error"]
