"""Resolve fan-out/depth benchmark orchestration."""

from __future__ import annotations

import httpx
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from workload.clients import (
    ConflictError,
    DppResponse,
    DppSchemaVersion,
    IssueDppSpec,
    PlatformClient,
    ResolverClient,
)
from workload.federation import FederationClient, PlatformStatus
from workload.payloads import ReferenceSpec

from .errors import BenchmarkSetupError, ResolveBenchmarkError
from .graph import generate_resolve_tree, reference_count
from .models import (
    BenchmarkNode,
    PlatformInfo,
    ResolveCallError,
    ResolveFanoutConfig,
    ResolveMeasurementSummary,
)
from .stats import summarize_latencies

DEFAULT_PLATFORM_STACK = "spring-postgres"
ProgressCallback = Callable[[str, int], None]


async def run_resolve_fanout_benchmark(
    config: ResolveFanoutConfig,
    *,
    federation_client: FederationClient | None = None,
    resolver_client_factory: Callable[[str], ResolverClient] = ResolverClient,
    platform_client_factory: Callable[[PlatformInfo], PlatformClient] = PlatformClient,
    timer_ns: Callable[[], int] = time.perf_counter_ns,
    progress_callback: ProgressCallback | None = None,
) -> ResolveMeasurementSummary:
    """Run the resolve fan-out benchmark and return summary statistics."""
    _validate_config(config)
    run_id = _run_id(config)
    max_resolved_depth = effective_max_resolved_depth(config)
    total_revisions = 1 + reference_count(config.fanout, config.depth)

    owns_federation_client = federation_client is None
    fed_client = federation_client or FederationClient(timeout=config.timeout_seconds)

    resolver_client: ResolverClient | None = None
    try:
        resolver_url, platforms, existing_count, created_count = await _ensure_platforms(
            fed_client=fed_client,
            config=config,
            run_id=run_id,
            resolver_client_factory=resolver_client_factory,
            progress_callback=progress_callback,
        )
        resolver_client = resolver_client_factory(resolver_url)
        subject_types = await _ensure_subject_types(
            resolver=resolver_client,
            platforms=platforms,
            run_id=run_id,
            payload_entries=config.payload_entries,
            platform_client_factory=platform_client_factory,
            progress_callback=progress_callback,
        )

        nodes = generate_resolve_tree(
            fanout=config.fanout,
            depth=config.depth,
            platforms=platforms,
            run_id=run_id,
        )
        root = nodes[0]
        platform_by_id = {platform.platform_id: platform for platform in platforms}
        await _publish_revisions(
            nodes=nodes,
            platforms=platforms,
            payload_entries=config.payload_entries,
            platform_client_factory=platform_client_factory,
            progress_callback=progress_callback,
        )

        for warmup_index in range(config.warmup):
            _print_verbose_resolve_start(
                config,
                phase="warmup",
                index=warmup_index + 1,
                total=config.warmup,
                root=root,
                max_resolved_depth=max_resolved_depth,
            )
            try:
                latency_ms = await _resolve_once(
                    resolver_client,
                    root,
                    platform_by_id[root.platform_id],
                    max_resolved_depth,
                    timer_ns,
                )
                _print_verbose_resolve_end(
                    config,
                    phase="warmup",
                    index=warmup_index + 1,
                    total=config.warmup,
                    latency_ms=latency_ms,
                )
                _report_progress(
                    progress_callback,
                    f"Warmup resolve calls {warmup_index + 1}/{config.warmup}",
                )
            except Exception as exc:
                _print_verbose_resolve_error(
                    config,
                    phase="warmup",
                    index=warmup_index + 1,
                    total=config.warmup,
                    message=_error_message(exc, config.verbose_errors),
                )
                raise ResolveBenchmarkError(
                    f"Warmup resolve call {warmup_index + 1} failed: {_error_message(exc, config.verbose_errors)}"
                ) from exc

        latencies_ms: list[float] = []
        errors: list[ResolveCallError] = []
        for sample in range(1, config.samples + 1):
            _print_verbose_resolve_start(
                config,
                phase="sample",
                index=sample,
                total=config.samples,
                root=root,
                max_resolved_depth=max_resolved_depth,
            )
            try:
                latency_ms = await _resolve_once(
                    resolver_client,
                    root,
                    platform_by_id[root.platform_id],
                    max_resolved_depth,
                    timer_ns,
                )
                latencies_ms.append(latency_ms)
                _print_verbose_resolve_end(
                    config,
                    phase="sample",
                    index=sample,
                    total=config.samples,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                message = _error_message(exc, config.verbose_errors)
                _print_verbose_resolve_error(
                    config,
                    phase="sample",
                    index=sample,
                    total=config.samples,
                    message=message,
                )
                errors.append(
                    ResolveCallError(
                        sample=sample,
                        message=message,
                    )
                )
            finally:
                _report_progress(progress_callback, f"Measured resolve calls {sample}/{config.samples}")

        stats = summarize_latencies(latencies_ms)
        return ResolveMeasurementSummary(
            fanout=config.fanout,
            depth=config.depth,
            max_resolved_depth=max_resolved_depth,
            platform_count=config.platform_count,
            total_revisions=total_revisions,
            payload_entries=config.payload_entries,
            samples=config.samples,
            warmup=config.warmup,
            successful_calls=len(latencies_ms),
            errors=len(errors),
            median_ms=stats.median_ms,
            mean_ms=stats.mean_ms,
            min_ms=stats.min_ms,
            max_ms=stats.max_ms,
            p90_ms=stats.p90_ms,
            p95_ms=stats.p95_ms,
            p99_ms=stats.p99_ms,
            resolver_url=resolver_url,
            existing_platforms=existing_count,
            created_platforms=created_count,
            subject_types=len(subject_types),
            root_revision=root.node_id,
            error_details=tuple(errors),
        )
    finally:
        if resolver_client is not None:
            await resolver_client.close()
        if owns_federation_client:
            await fed_client.close()


def _validate_config(config: ResolveFanoutConfig) -> None:
    if config.fanout < 1:
        raise ValueError("fanout must be >= 1")
    if config.depth < 1:
        raise ValueError("depth must be >= 1")
    if config.platform_count < 2:
        raise ValueError("platforms must be >= 2")
    if config.samples < 1:
        raise ValueError("samples must be >= 1")
    if config.warmup < 0:
        raise ValueError("warmup must be >= 0")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout must be > 0")
    if config.payload_entries < 1:
        raise ValueError("payload-entries must be >= 1")
    max_resolved_depth = effective_max_resolved_depth(config)
    if max_resolved_depth < 1:
        raise ValueError("max-resolved-depth must be >= 1")
    if max_resolved_depth > config.depth:
        raise ValueError("max-resolved-depth must not exceed depth")


def effective_max_resolved_depth(config: ResolveFanoutConfig) -> int:
    """Return the resolved closure depth, defaulting to the generated tree depth."""
    return config.depth if config.max_resolved_depth is None else config.max_resolved_depth


def _run_id(config: ResolveFanoutConfig) -> str:
    if config.seed:
        return _slug(config.seed)
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def _issuer_run_id(run_id: str) -> str:
    return "".join(char for char in run_id if char.isalnum()) or "run"


def _slug(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value).strip("-").lower() or "run"


async def _ensure_platforms(
    *,
    fed_client: FederationClient,
    config: ResolveFanoutConfig,
    run_id: str,
    resolver_client_factory: Callable[[str], ResolverClient],
    progress_callback: ProgressCallback | None,
) -> tuple[str, tuple[PlatformInfo, ...], int, int]:
    overview = await fed_client.discover(config.factory_url)
    if not overview.resolver:
        raise BenchmarkSetupError("Factory has no resolver in its federation state.")

    resolver_url = overview.resolver.external_url
    running = [_to_measurement_platform(platform) for platform in overview.platforms if _is_usable_platform(platform)]
    existing_count = len(running)
    created_count = 0
    _report_progress(
        progress_callback,
        f"Discovered {min(existing_count, config.platform_count)} usable platforms",
        advance=1 + min(existing_count, config.platform_count),
    )

    while len(running) < config.platform_count:
        index = len(running)
        subject_type = f"bench-resolve-{run_id}-type-{index}"
        issuer_id = f"benchresolve{_issuer_run_id(run_id)}issuer{index}"
        setup_resolver = resolver_client_factory(resolver_url)
        try:
            await setup_resolver.ensure_subject_type(subject_type)
        finally:
            await setup_resolver.close()
        try:
            await fed_client.create_platform(
                config.factory_url,
                stack=DEFAULT_PLATFORM_STACK,
                issuer_id=issuer_id,
                subject_types=[subject_type],
            )
        except Exception as exc:
            raise BenchmarkSetupError(
                f"Failed to create benchmark platform for {subject_type}: {_error_message(exc, True)}"
            ) from exc
        created_count += 1
        _report_progress(
            progress_callback,
            f"Created benchmark platforms {created_count}/{config.platform_count - existing_count}",
        )
        overview = await fed_client.refresh(config.factory_url)
        if not overview.resolver:
            raise BenchmarkSetupError("Factory lost resolver information after platform creation.")
        resolver_url = overview.resolver.external_url
        running = [_to_measurement_platform(platform) for platform in overview.platforms if _is_usable_platform(platform)]

    if len(running) < config.platform_count:
        raise BenchmarkSetupError(
            f"Only {len(running)} running platforms available; {config.platform_count} required."
        )
    return resolver_url, tuple(running[: config.platform_count]), existing_count, created_count


def _is_running(platform: Any) -> bool:
    status = getattr(platform, "status", None)
    if status == PlatformStatus.RUNNING:
        return True
    value = getattr(status, "value", status)
    return str(value).upper() == "RUNNING"


def _is_usable_platform(platform: Any) -> bool:
    """Return true for platforms whose issuer can be parsed by the Resolver."""
    issuer_id = str(getattr(platform, "issuer_id", ""))
    return _is_running(platform) and "-" not in issuer_id


def _to_measurement_platform(platform: Any) -> PlatformInfo:
    return PlatformInfo(
        platform_id=str(platform.platform_id),
        issuer_id=str(platform.issuer_id),
        subject_types=tuple(platform.subject_types),
        external_url=str(platform.external_url),
        internal_url=str(getattr(platform, "internal_url", "")) or None,
    )


async def _ensure_subject_types(
    *,
    resolver: ResolverClient,
    platforms: Sequence[PlatformInfo],
    run_id: str,
    payload_entries: int,
    platform_client_factory: Callable[[PlatformInfo], PlatformClient],
    progress_callback: ProgressCallback | None,
) -> tuple[str, ...]:
    subject_types: list[str] = []
    for index, platform in enumerate(platforms):
        subject_type = f"bench-resolve-{run_id}-type-{index}"
        subject_types.append(subject_type)
        await resolver.ensure_subject_type(subject_type)
        await resolver.publish_schema(
            subject_type,
            1,
            0,
            _generate_benchmark_schema(subject_type, payload_entries=payload_entries),
        )
        await resolver.ensure_platform_route(platform, subject_type)
        async with platform_client_factory(platform) as platform_client:
            await platform_client.ensure_subject_type(subject_type)
        _report_progress(progress_callback, f"Prepared subject types {index + 1}/{len(platforms)}")
    return tuple(subject_types)


async def _publish_revisions(
    *,
    nodes: Sequence[BenchmarkNode],
    platforms: Sequence[PlatformInfo],
    payload_entries: int,
    platform_client_factory: Callable[[PlatformInfo], PlatformClient],
    progress_callback: ProgressCallback | None,
) -> tuple[DppResponse, ...]:
    node_by_id = {node.node_id: node for node in nodes}
    platform_by_id = {platform.platform_id: platform for platform in platforms}
    responses: list[DppResponse] = []

    ordered_nodes = sorted(nodes, key=lambda item: item.depth, reverse=True)
    for index, node in enumerate(ordered_nodes, start=1):
        platform = platform_by_id[node.platform_id]
        references = [
            ReferenceSpec(
                subject_type=node_by_id[child_id].subject_type,
                dpp_id=child_id,
                version=1,
            )
            for child_id in node.children
        ]
        payload = _build_benchmark_payload(
            node_id=node.node_id,
            issuer_id=node.issuer_id,
            subject_type=node.subject_type,
            hard_references=references,
            payload_entries=payload_entries,
        )
        spec = IssueDppSpec(
            dpp_id=node.node_id,
            schema_version=DppSchemaVersion(
                subject_type=node.subject_type,
                major_version=1,
                minor_version=0,
            ),
            dpp_payload=payload,
        )
        try:
            async with platform_client_factory(platform) as platform_client:
                responses.append(await platform_client.issue_dpp(spec))
        except ConflictError:
            async with platform_client_factory(platform) as platform_client:
                responses.append(await platform_client.get_revision(node.node_id, 1))
        except Exception as exc:
            raise BenchmarkSetupError(
                f"Failed to publish {node.node_id} to {platform.external_url}: {_error_message(exc, True)}"
            ) from exc
        _report_progress(progress_callback, f"Published revisions {index}/{len(ordered_nodes)}")
    return tuple(responses)


def _generate_benchmark_schema(subject_type: str, *, payload_entries: int) -> dict:
    properties = {
        f"payload_entry_{index:03d}": {"type": "string"}
        for index in range(payload_entries)
    }
    properties["dependencies"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "$ref": {"type": "string", "pattern": "^[^/]+/[^/]+(?:/\\d+)?$"},
                "version": {"type": "integer", "minimum": 1},
            },
            "required": ["$ref"],
            "additionalProperties": False,
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://dpp.example.org/schemas/{subject_type}",
        "title": f"Benchmark DPP Schema for {subject_type}",
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }


def _build_benchmark_payload(
    *,
    node_id: str,
    issuer_id: str,
    subject_type: str,
    hard_references: Sequence[ReferenceSpec],
    payload_entries: int,
) -> dict:
    data_entry_count = payload_entries if not hard_references else payload_entries - 1
    payload = {
        f"payload_entry_{index:03d}": f"{issuer_id}:{subject_type}:{node_id}:{index:03d}"
        for index in range(data_entry_count)
    }
    if hard_references:
        payload["dependencies"] = []
        for reference in hard_references:
            entry: dict[str, Any] = {"$ref": f"{reference.subject_type}/{reference.dpp_id}"}
            if reference.version is not None:
                entry["version"] = reference.version
            payload["dependencies"].append(entry)
    return payload


async def _resolve_once(
    resolver: ResolverClient,
    root: BenchmarkNode,
    root_platform: PlatformInfo,
    max_resolved_depth: int,
    timer_ns: Callable[[], int],
) -> float:
    start_ns = timer_ns()
    response = await resolver.resolve_revision_closure(
        root.subject_type,
        root.node_id,
        version=1,
        max_depth=max_resolved_depth,
        redirect_base_url=root_platform.external_url,
    )
    end_ns = timer_ns()

    body = response.content
    if root.node_id.encode("utf-8") not in body:
        raise ResolveBenchmarkError(f"Resolve response did not contain root revision {root.node_id}.")
    return (end_ns - start_ns) / 1_000_000


def _print_verbose_resolve_start(
    config: ResolveFanoutConfig,
    *,
    phase: str,
    index: int,
    total: int,
    root: BenchmarkNode,
    max_resolved_depth: int,
) -> None:
    if config.verbose:
        print(
            "\n"
            f"=== closure {phase} {index}/{total} "
            f"root={root.subject_type}/{root.node_id}/1 "
            f"max_depth={max_resolved_depth} ===",
            flush=True,
        )


def _print_verbose_resolve_end(
    config: ResolveFanoutConfig,
    *,
    phase: str,
    index: int,
    total: int,
    latency_ms: float,
) -> None:
    if config.verbose:
        print(
            f"=== closure {phase} {index}/{total} completed: {latency_ms:.2f} ms ===",
            flush=True,
        )


def _print_verbose_resolve_error(
    config: ResolveFanoutConfig,
    *,
    phase: str,
    index: int,
    total: int,
    message: str,
) -> None:
    if config.verbose:
        print(f"=== closure {phase} {index}/{total} failed: {message} ===", flush=True)


def _error_message(exc: Exception, verbose: bool) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        text = response.text if verbose else response.text[:200]
        return f"HTTP {response.status_code}: {text}"
    if verbose:
        return repr(exc)
    return str(exc)


def _report_progress(
    progress_callback: ProgressCallback | None,
    description: str,
    advance: int = 1,
) -> None:
    if progress_callback is not None:
        progress_callback(description, advance)
