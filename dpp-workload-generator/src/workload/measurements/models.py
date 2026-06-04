"""Typed value objects for workload measurements."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ResolveFanoutConfig:
    """Configuration for the resolve fan-out/depth benchmark."""

    factory_url: str
    fanout: int
    depth: int
    platform_count: int
    samples: int
    warmup: int
    timeout_seconds: float
    seed: str | None
    verbose_errors: bool
    verbose: bool = False


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """DPP platform details needed by the benchmark."""

    platform_id: str
    issuer_id: str
    subject_types: tuple[str, ...]
    external_url: str
    internal_url: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkNode:
    """A deterministic DPP revision node in the benchmark tree."""

    node_id: str
    subject_type: str
    issuer_id: str
    platform_id: str
    depth: int
    children: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LatencyStats:
    """Latency statistics in milliseconds."""

    median_ms: float | None
    mean_ms: float | None
    min_ms: float | None
    max_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p99_ms: float | None


@dataclass(frozen=True, slots=True)
class ResolveCallError:
    """Compact error information for a failed measured resolve call."""

    sample: int
    message: str


@dataclass(frozen=True, slots=True)
class ResolveMeasurementSummary:
    """Summary returned by the resolve fan-out benchmark."""

    fanout: int
    depth: int
    platform_count: int
    total_revisions: int
    samples: int
    warmup: int
    successful_calls: int
    errors: int
    median_ms: float | None
    mean_ms: float | None
    min_ms: float | None
    max_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    resolver_url: str | None = None
    existing_platforms: int = 0
    created_platforms: int = 0
    subject_types: int = 0
    root_revision: str | None = None
    error_details: tuple[ResolveCallError, ...] = field(default_factory=tuple)
