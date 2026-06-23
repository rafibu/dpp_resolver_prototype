"""Shared, HTTP-friendly result types for workload scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkloadScenarioStep:
    """One externally reportable workload-scenario step."""

    name: str
    status: str
    error: str | None = None


@dataclass(frozen=True)
class WorkloadScenarioResult:
    """Structured scenario outcome usable by the CLI and a Factory adapter."""

    scenario_id: str
    success: bool
    steps: tuple[WorkloadScenarioStep, ...] = ()
    observations: tuple[str, ...] = ()
    report_md: str | None = None
    summary: dict[str, Any] | None = None
