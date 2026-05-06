import csv
import os
import time
import structlog
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

logger = structlog.get_logger(__name__)

class MeasurementRecorder:
    def __init__(self, output_dir: Optional[str] = None):
        if output_dir is None:
            output_dir = os.environ.get("WORKLOAD_OUTPUT_DIR", "output")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id: Optional[str] = None
        self.workload_kind: Optional[str] = None
        self.records: List[Dict[str, Any]] = []

    def start_run(self, run_id: str, workload_kind: str):
        self.run_id = run_id
        self.workload_kind = workload_kind
        self.records = []
        logger.info("start_run", run_id=run_id, workload_kind=workload_kind)

    def record(self, operation: str, parameter_value: int, latency_ms: float, 
               bytes_payload: int = 0, bytes_index: int = 0, 
               success: bool = True, error: str | None = None, warmup: bool = False):
        record = {
            "run_id": self.run_id,
            "workload_kind": self.workload_kind,
            "parameter_value": parameter_value,
            "operation": operation,
            "latency_ms": latency_ms,
            "bytes_payload": bytes_payload,
            "bytes_index": bytes_index,
            "success": success,
            "error": error,
            "warmup": warmup
        }
        self.records.append(record)
        logger.debug("recorded_operation", operation=operation, latency_ms=latency_ms, success=success)

    def end_run(self) -> Path:
        if not self.workload_kind:
            raise RuntimeError("Run not started")
            
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{self.workload_kind}-{timestamp}.csv"
        path = self.output_dir / filename
        
        fieldnames = ["run_id", "workload_kind", "parameter_value", "operation", 
                      "latency_ms", "bytes_payload", "bytes_index", "success", "error", "warmup"]
        
        with open(path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.records)
            
        logger.info("run_ended", path=str(path), row_count=len(self.records))
        return path

class MeasurementContext:
    def __init__(self):
        self.bytes_payload = 0
        self.bytes_index = 0

@asynccontextmanager
async def measure_operation(recorder: MeasurementRecorder, operation: str, parameter_value: int, warmup: bool = False):
    """Context manager to time a block and record it in the recorder."""
    ctx = MeasurementContext()
    start_time = time.perf_counter()
    success = True
    error = None
    try:
        yield ctx
    except Exception as e:
        success = False
        error = str(e)
        raise
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000
        recorder.record(
            operation=operation,
            parameter_value=parameter_value,
            latency_ms=latency_ms,
            bytes_payload=ctx.bytes_payload,
            bytes_index=ctx.bytes_index,
            success=success,
            error=error,
            warmup=warmup
        )
