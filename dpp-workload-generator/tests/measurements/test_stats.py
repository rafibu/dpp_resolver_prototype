from workload.measurements.stats import summarize_latencies


def test_summarize_latencies_uses_nearest_rank_percentiles():
    stats = summarize_latencies([10.0, 20.0, 30.0, 40.0, 50.0])

    assert stats.min_ms == 10.0
    assert stats.max_ms == 50.0
    assert stats.median_ms == 30.0
    assert stats.mean_ms == 30.0
    assert stats.p90_ms == 50.0
    assert stats.p95_ms == 50.0
    assert stats.p99_ms == 50.0


def test_summarize_latencies_empty_input():
    stats = summarize_latencies([])

    assert stats.median_ms is None
    assert stats.mean_ms is None
    assert stats.min_ms is None
    assert stats.max_ms is None
    assert stats.p90_ms is None
    assert stats.p95_ms is None
    assert stats.p99_ms is None

