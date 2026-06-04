from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch
from workload.cli import app
from workload.measurements.models import ResolveMeasurementSummary


def test_resolve_fanout_cli_outputs_summary():
    runner = CliRunner()
    summary = ResolveMeasurementSummary(
        fanout=1,
        depth=1,
        max_resolved_depth=1,
        platform_count=2,
        total_revisions=2,
        samples=2,
        warmup=1,
        successful_calls=2,
        errors=0,
        median_ms=10.0,
        mean_ms=11.0,
        min_ms=9.0,
        max_ms=12.0,
        p90_ms=12.0,
        p95_ms=12.0,
        p99_ms=12.0,
        resolver_url="http://resolver",
        existing_platforms=2,
        created_platforms=0,
        subject_types=2,
        root_revision="issuer0-bench-resolve-cli-f1-d1-root",
    )

    benchmark = AsyncMock(return_value=summary)
    with patch("workload.measurements.cli.run_resolve_fanout_benchmark", new=benchmark):
        result = runner.invoke(
            app,
            [
                "measure",
                "resolve-fanout",
                "--fanout",
                "1",
                "--depth",
                "1",
                "--platforms",
                "2",
                "--samples",
                "2",
                "--warmup",
                "1",
                "--seed",
                "cli",
            ],
        )

    assert result.exit_code == 0
    assert "Resolve fan-out benchmark" in result.output
    assert "Median" in result.output
    assert "Successful calls" in result.output
    assert "Generated depth" in result.output
    assert "Max resolved depth" in result.output
    assert benchmark.call_args.args[0].max_resolved_depth is None
    assert "progress_callback" in benchmark.call_args.kwargs


def test_resolve_fanout_cli_verbose_short_flag_disables_progress_callback():
    runner = CliRunner()
    summary = ResolveMeasurementSummary(
        fanout=1,
        depth=1,
        max_resolved_depth=1,
        platform_count=2,
        total_revisions=2,
        samples=1,
        warmup=0,
        successful_calls=1,
        errors=0,
        median_ms=10.0,
        mean_ms=10.0,
        min_ms=10.0,
        max_ms=10.0,
        p90_ms=10.0,
        p95_ms=10.0,
        p99_ms=10.0,
    )
    benchmark = AsyncMock(return_value=summary)

    with patch("workload.measurements.cli.run_resolve_fanout_benchmark", new=benchmark):
        result = runner.invoke(
            app,
            [
                "measure",
                "resolve-fanout",
                "--fanout",
                "1",
                "--depth",
                "1",
                "--platforms",
                "2",
                "--samples",
                "1",
                "--warmup",
                "0",
                "-v",
            ],
        )

    assert result.exit_code == 0
    assert benchmark.call_args.args[0].verbose is True
    assert "progress_callback" not in benchmark.call_args.kwargs


def test_resolve_fanout_cli_accepts_explicit_max_resolved_depth():
    runner = CliRunner()
    summary = ResolveMeasurementSummary(
        fanout=2,
        depth=4,
        max_resolved_depth=1,
        platform_count=2,
        total_revisions=31,
        samples=1,
        warmup=0,
        successful_calls=1,
        errors=0,
        median_ms=10.0,
        mean_ms=10.0,
        min_ms=10.0,
        max_ms=10.0,
        p90_ms=10.0,
        p95_ms=10.0,
        p99_ms=10.0,
    )
    benchmark = AsyncMock(return_value=summary)

    with patch("workload.measurements.cli.run_resolve_fanout_benchmark", new=benchmark):
        result = runner.invoke(
            app,
            [
                "measure",
                "resolve-fanout",
                "--fanout",
                "2",
                "--depth",
                "4",
                "--platforms",
                "2",
                "--samples",
                "1",
                "--warmup",
                "0",
                "--max-resolved-depth",
                "1",
            ],
        )

    assert result.exit_code == 0
    assert benchmark.call_args.args[0].max_resolved_depth == 1
    assert "Max resolved depth:1" in result.output


def test_resolve_fanout_cli_accepts_explicit_payload_entries():
    runner = CliRunner()
    summary = ResolveMeasurementSummary(
        fanout=1,
        depth=2,
        max_resolved_depth=2,
        platform_count=2,
        total_revisions=3,
        payload_entries=8,
        samples=1,
        warmup=0,
        successful_calls=1,
        errors=0,
        median_ms=10.0,
        mean_ms=10.0,
        min_ms=10.0,
        max_ms=10.0,
        p90_ms=10.0,
        p95_ms=10.0,
        p99_ms=10.0,
    )
    benchmark = AsyncMock(return_value=summary)

    with patch("workload.measurements.cli.run_resolve_fanout_benchmark", new=benchmark):
        result = runner.invoke(
            app,
            [
                "measure",
                "resolve-fanout",
                "--fanout",
                "1",
                "--depth",
                "2",
                "--platforms",
                "2",
                "--samples",
                "1",
                "--warmup",
                "0",
                "--payload-entries",
                "8",
            ],
        )

    assert result.exit_code == 0
    assert benchmark.call_args.args[0].payload_entries == 8
    assert "Payload entries:   8" in result.output


def test_resolve_fanout_cli_rejects_invalid_max_resolved_depth():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "measure",
            "resolve-fanout",
            "--fanout",
            "1",
            "--depth",
            "2",
            "--platforms",
            "2",
            "--samples",
            "1",
            "--warmup",
            "0",
            "--max-resolved-depth",
            "0",
        ],
    )

    assert result.exit_code == 1
    assert "max-resolved-depth must be >= 1" in result.output


def test_resolve_fanout_cli_rejects_invalid_payload_entries():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "measure",
            "resolve-fanout",
            "--fanout",
            "1",
            "--depth",
            "2",
            "--platforms",
            "2",
            "--samples",
            "1",
            "--warmup",
            "0",
            "--payload-entries",
            "0",
        ],
    )

    assert result.exit_code == 1
    assert "payload-entries must be >= 1" in result.output


def test_resolve_fanout_cli_rejects_max_resolved_depth_above_depth():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "measure",
            "resolve-fanout",
            "--fanout",
            "1",
            "--depth",
            "2",
            "--platforms",
            "2",
            "--samples",
            "1",
            "--warmup",
            "0",
            "--max-resolved-depth",
            "3",
        ],
    )

    assert result.exit_code == 1
    assert "max-resolved-depth must not exceed depth" in result.output
