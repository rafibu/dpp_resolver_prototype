"""Latency statistics helpers for workload measurements."""

import math
import statistics
from collections.abc import Sequence

from .models import LatencyStats


def summarize_latencies(latencies_ms: Sequence[float]) -> LatencyStats:
    """Summarize latencies using nearest-rank percentiles."""
    if not latencies_ms:
        return LatencyStats(
            median_ms=None,
            mean_ms=None,
            min_ms=None,
            max_ms=None,
            p90_ms=None,
            p95_ms=None,
            p99_ms=None,
        )

    values = sorted(float(value) for value in latencies_ms)
    return LatencyStats(
        median_ms=statistics.median(values),
        mean_ms=statistics.fmean(values),
        min_ms=values[0],
        max_ms=values[-1],
        p90_ms=_nearest_rank(values, 90),
        p95_ms=_nearest_rank(values, 95),
        p99_ms=_nearest_rank(values, 99),
    )


def _nearest_rank(sorted_values: Sequence[float], percentile: int) -> float:
    rank = math.ceil((percentile / 100) * len(sorted_values))
    index = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[index]

