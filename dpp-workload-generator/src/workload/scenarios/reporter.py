import os
import time
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ScenarioStep(BaseModel):
    id: int
    description: str
    expected: str
    observed: str = "Not recorded"
    success: bool = False
    details: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0

class ScenarioResult(BaseModel):
    scenario_id: str
    scenario_title: str
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps: List[ScenarioStep] = []
    outcome: str = "PENDING"

class ScenarioReporter:
    def __init__(self, scenario_id: str, scenario_title: str, output_dir: Optional[Path] = None):
        now = datetime.now(timezone.utc)
        self.result = ScenarioResult(
            scenario_id=scenario_id,
            scenario_title=scenario_title,
            run_id=f"{scenario_id}-{now.strftime('%Y-%m-%dT%H-%M-%SZ')}",
            started_at=now
        )
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = Path(os.getenv("WORKLOAD_OUTPUT_DIR", "output/scenarios"))
        
        self._current_step: Optional[ScenarioStep] = None

    @contextmanager
    def step(self, description: str, expected: str):
        step_id = len(self.result.steps) + 1
        self._current_step = ScenarioStep(id=step_id, description=description, expected=expected)
        start_time = time.perf_counter()
        try:
            yield
        except Exception as e:
            if self._current_step:
                self._current_step.observed = f"Exception: {type(e).__name__}: {str(e)}"
                self._current_step.success = False
            # We don't re-raise because the task says "the scenario continues to the end"
        finally:
            duration = (time.perf_counter() - start_time) * 1000
            if self._current_step:
                self._current_step.duration_ms = duration
                self.result.steps.append(self._current_step)
                self._current_step = None

    def record_observation(self, observed: str, success: bool, details: Optional[Dict[str, Any]] = None):
        if self._current_step:
            self._current_step.observed = observed
            self._current_step.success = success
            self._current_step.details = details

    def finalize(self) -> Path:
        self.result.completed_at = datetime.now(timezone.utc)
        self.result.outcome = "PASSED" if all(s.success for s in self.result.steps) else "FAILED"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.result.run_id}.md"
        report_path = self.output_dir / filename
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self._generate_markdown())
            
        return report_path

    def _generate_markdown(self) -> str:
        md = [
            f"# Scenario {self.result.scenario_id.upper()}: {self.result.scenario_title}",
            "",
            f"**Run ID:** {self.result.run_id}",
            f"**Started:** {self.result.started_at.isoformat().replace('+00:00', 'Z')}",
            f"**Completed:** {self.result.completed_at.isoformat().replace('+00:00', 'Z')}",
            f"**Outcome:** {self.result.outcome}",
            "",
            "## Steps",
            ""
        ]
        
        for step in self.result.steps:
            md.append(f"### Step {step.id}: {step.description}")
            md.append("")
            md.append(f"**Expected:** {step.expected}")
            md.append("")
            md.append(f"**Observed:** {step.observed}")
            md.append("")
            md.append(f"**Result:** {'PASSED' if step.success else 'FAILED'}")
            md.append(f"**Duration:** {step.duration_ms:.2f}ms")
            if step.details:
                md.append("")
                md.append("**Details:**")
                md.append("```json")
                import json
                md.append(json.dumps(step.details, indent=2))
                md.append("```")
            md.append("")
        
        # Verification section for formal model elements (as requested in example)
        md.append("## Verification of formal-model elements")
        md.append("")
        # This part is scenario-specific, but I can add placeholders or a way to record them.
        # For now, let's keep it simple as the reporter is shared.
        
        md.append("## Conclusion")
        md.append("")
        md.append(f"Scenario {self.result.scenario_id.upper()} {self.result.outcome.lower()} successfully.")

        return "\n".join(md)
