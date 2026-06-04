"""Typer command registration for workload measurements."""

from __future__ import annotations

import asyncio
import io
import sys
import typer
from collections.abc import Awaitable, Callable
from contextlib import redirect_stdout
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from typing import Optional

from .errors import MeasurementError
from .graph import reference_count
from .models import ResolveFanoutConfig, ResolveMeasurementSummary
from .resolve_fanout import run_resolve_fanout_benchmark

LegacyMeasureRunner = Callable[[str, str, int, int, Optional[str], int, str], Awaitable[None]]


def build_measure_app(legacy_runner: LegacyMeasureRunner | None = None) -> typer.Typer:
    """Build the grouped measurement command app."""
    measure_app = typer.Typer(help="Run a parameterized measurement or benchmark mechanism.")

    @measure_app.callback(invoke_without_command=True)
    def measure_callback(
        ctx: typer.Context,
        workload: Optional[str] = typer.Option(None, "--workload", help="Workload kind: depth, fanout, issue, resolve, query"),
        range_str: str = typer.Option("1-10", "--range", help="Parameter range (e.g. 1-10)"),
        runs: int = typer.Option(5, "--runs", help="Number of measurement runs per value"),
        warmup_runs: int = typer.Option(1, "--warmup-runs", help="Number of warmup runs (not recorded)"),
        output: Optional[str] = typer.Option(None, "--output", help="Output path for CSV"),
        seed: int = typer.Option(42, "--seed", help="Random seed"),
        factory_url: str = typer.Option("http://localhost:8000", "--factory-url", help="Factory URL"),
    ) -> None:
        """Run a parameterized measurement, or choose a benchmark subcommand."""
        if ctx.invoked_subcommand is not None:
            return
        if workload is None:
            typer.echo(ctx.get_help())
            raise typer.Exit()
        if legacy_runner is None:
            raise typer.BadParameter("legacy measurement runner is not configured")
        asyncio.run(legacy_runner(workload, range_str, runs, warmup_runs, output, seed, factory_url))

    @measure_app.command("resolve-fanout")
    def resolve_fanout(
        factory_url: str = typer.Option("http://localhost:8000", "--factory-url", help="URL of the running platform factory"),
        fanout: int = typer.Option(2, "--fanout", help="Number of hard references per node"),
        depth: int = typer.Option(2, "--depth", help="Number of reference levels below root"),
        platforms: int = typer.Option(4, "--platforms", help="Total number of DPP platforms required"),
        samples: int = typer.Option(100, "--samples", help="Measured resolve calls"),
        warmup: int = typer.Option(20, "--warmup", help="Warmup resolve calls excluded from statistics"),
        timeout: float = typer.Option(30.0, "--timeout", help="HTTP timeout in seconds"),
        seed: Optional[str] = typer.Option(None, "--seed", help="Deterministic seed / run ID"),
        verbose: bool = typer.Option(False, "-v", "--verbose", help="Show individual API calls instead of the progress bar"),
        verbose_errors: bool = typer.Option(False, "--verbose-errors", help="Print detailed error payloads on failure"),
    ) -> None:
        """Measure resolver latency for a deterministic hard-reference tree."""
        config = ResolveFanoutConfig(
            factory_url=factory_url,
            fanout=fanout,
            depth=depth,
            platform_count=platforms,
            samples=samples,
            warmup=warmup,
            timeout_seconds=timeout,
            seed=seed,
            verbose_errors=verbose_errors,
            verbose=verbose,
        )
        typer.echo(_render_configuration(config))
        try:
            summary = _run_with_output_mode(config)
        except (MeasurementError, ValueError) as exc:
            typer.echo("\nSetup error")
            typer.echo(f"  {exc}")
            raise typer.Exit(code=1) from exc

        typer.echo(_render_summary(summary))
        if summary.errors > 0 or summary.successful_calls == 0:
            raise typer.Exit(code=1)

    return measure_app


def _run_with_output_mode(config: ResolveFanoutConfig) -> ResolveMeasurementSummary:
    if config.verbose:
        return asyncio.run(run_resolve_fanout_benchmark(config))

    total_steps = _progress_total(config)
    console = Console(file=sys.stderr)
    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Preparing benchmark", total=total_steps)

        def progress_callback(description: str, advance: int) -> None:
            progress.update(task_id, description=description, advance=advance)

        with redirect_stdout(io.StringIO()):
            return asyncio.run(
                run_resolve_fanout_benchmark(
                    config,
                    progress_callback=progress_callback,
                )
            )


def _progress_total(config: ResolveFanoutConfig) -> int:
    total_revisions = 1 + reference_count(config.fanout, config.depth)
    return 1 + config.platform_count + config.platform_count + total_revisions + config.warmup + config.samples


def _render_configuration(config: ResolveFanoutConfig) -> str:
    total_revisions = 1 + reference_count(config.fanout, config.depth)
    return "\n".join(
        [
            "Resolve fan-out benchmark",
            "",
            "Configuration",
            f"  Factory URL:       {config.factory_url}",
            f"  Fan-out:           {config.fanout}",
            f"  Depth:             {config.depth}",
            f"  Required platforms:{config.platform_count}",
            f"  Total revisions:   {total_revisions}",
            f"  Warmup calls:      {config.warmup}",
            f"  Samples:           {config.samples}",
        ]
    )


def _render_summary(summary: ResolveMeasurementSummary) -> str:
    lines = [
        "",
        "Setup",
        f"  Resolver:          {summary.resolver_url or 'n/a'}",
        f"  Existing platforms:{summary.existing_platforms}",
        f"  Created platforms: {summary.created_platforms}",
        f"  Subject types:     {summary.subject_types}",
        f"  Root revision:     {summary.root_revision or 'n/a'}",
        "",
        "Result",
        f"  Successful calls:  {summary.successful_calls} / {summary.samples}",
        f"  Errors:            {summary.errors}",
        f"  Median:            {_format_ms(summary.median_ms)}",
        f"  Mean:              {_format_ms(summary.mean_ms)}",
        f"  Min:               {_format_ms(summary.min_ms)}",
        f"  Max:               {_format_ms(summary.max_ms)}",
        f"  P90:               {_format_ms(summary.p90_ms)}",
        f"  P95:               {_format_ms(summary.p95_ms)}",
        f"  P99:               {_format_ms(summary.p99_ms)}",
    ]
    if summary.errors:
        lines.extend(["", "Errors", f"  {summary.errors} calls failed.", "", "First errors:"])
        for error in summary.error_details[:3]:
            lines.append(f"  [sample={error.sample}] {error.message}")
    return "\n".join(lines)


def _format_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f} ms"
