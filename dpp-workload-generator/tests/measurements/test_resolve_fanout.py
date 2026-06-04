from __future__ import annotations

import httpx
import pytest
from dataclasses import dataclass
from datetime import UTC, datetime
from workload.clients import DppResponse
from workload.federation import FederationOverview, PlatformInfo, PlatformStatus, ResolverInfo
from workload.measurements.models import ResolveFanoutConfig
from workload.measurements.resolve_fanout import effective_max_resolved_depth, run_resolve_fanout_benchmark


def _factory_platform(index: int) -> PlatformInfo:
    return PlatformInfo(
        platform_id=f"platform-{index}",
        stack="spring-postgres",
        issuer_id=f"issuer{index}",
        subject_types=[f"existing-{index}"],
        external_url=f"http://platform-{index}",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(UTC),
    )


def _bad_benchmark_platform(index: int) -> PlatformInfo:
    return PlatformInfo(
        platform_id=f"platform-bad-{index}",
        stack="spring-postgres",
        issuer_id=f"bench-resolve-old-issuer-{index}",
        subject_types=[f"bench-resolve-old-type-{index}"],
        external_url=f"http://platform-bad-{index}",
        status=PlatformStatus.RUNNING,
        created_at=datetime.now(UTC),
    )


class FakeFederationClient:
    def __init__(self, platform_count: int):
        self.platforms = [_factory_platform(index) for index in range(platform_count)]
        self.created: list[dict[str, object]] = []
        self.closed = False

    async def discover(self, factory_url: str) -> FederationOverview:
        return self._overview()

    async def refresh(self, factory_url: str) -> FederationOverview:
        return self._overview()

    async def create_platform(self, factory_url: str, *, stack: str, issuer_id: str, subject_types: list[str]) -> PlatformInfo:
        platform = PlatformInfo(
            platform_id=f"platform-{len(self.platforms)}",
            stack=stack,
            issuer_id=issuer_id,
            subject_types=subject_types,
            external_url=f"http://platform-{len(self.platforms)}",
            status=PlatformStatus.RUNNING,
            created_at=datetime.now(UTC),
        )
        self.platforms.append(platform)
        self.created.append({"stack": stack, "issuer_id": issuer_id, "subject_types": subject_types})
        return platform

    async def close(self) -> None:
        self.closed = True

    def _overview(self) -> FederationOverview:
        return FederationOverview(
            resolver=ResolverInfo(external_url="http://resolver", status=PlatformStatus.RUNNING),
            platforms=self.platforms,
        )


class FakeResolverClient:
    def __init__(self, base_url: str, *, fail_on_calls: set[int] | None = None):
        self.base_url = base_url
        self.fail_on_calls = fail_on_calls or set()
        self.subject_types: list[str] = []
        self.schemas: list[str] = []
        self.routes: list[tuple[str, str]] = []
        self.resolve_calls = 0
        self.closure_calls: list[tuple[str, str, int | None, int, str | None]] = []
        self.closed = False

    async def ensure_subject_type(self, subject_type: str) -> None:
        self.subject_types.append(subject_type)

    async def publish_schema(self, subject_type: str, major: int, minor: int, document: dict) -> None:
        self.schemas.append(subject_type)

    async def ensure_platform_route(self, platform, subject_type: str) -> None:
        self.routes.append((platform.platform_id, subject_type))

    async def resolve_revision(
        self,
        subject_type: str,
        dpp_id: str,
        version: int | None = None,
        redirect_base_url: str | None = None,
    ) -> httpx.Response:
        self.resolve_calls += 1
        if self.resolve_calls in self.fail_on_calls:
            raise RuntimeError("resolver exploded")
        request = httpx.Request("GET", f"{self.base_url}/{subject_type}/{dpp_id}/{version}")
        return httpx.Response(200, content=f'{{"dpp_id":"{dpp_id}"}}', request=request)

    async def resolve_revision_closure(
        self,
        subject_type: str,
        dpp_id: str,
        *,
        version: int,
        max_depth: int,
        redirect_base_url: str | None = None,
    ) -> httpx.Response:
        self.resolve_calls += 1
        self.closure_calls.append((subject_type, dpp_id, version, max_depth, redirect_base_url))
        if self.resolve_calls in self.fail_on_calls:
            raise RuntimeError("resolver exploded")
        request = httpx.Request(
            "GET",
            f"{redirect_base_url}/dpps/{dpp_id}/{version}/closure?max_depth={max_depth}",
        )
        return httpx.Response(200, content=f'{{"dpp_id":"{dpp_id}"}}', request=request)

    async def close(self) -> None:
        self.closed = True


@dataclass
class PublishedRevision:
    platform_id: str
    dpp_id: str
    dependency_count: int
    payload_entry_count: int


class FakePlatformState:
    def __init__(self):
        self.subject_types: list[tuple[str, str]] = []
        self.published: list[PublishedRevision] = []


class FakePlatformClient:
    def __init__(self, platform, state: FakePlatformState):
        self.platform = platform
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    async def ensure_subject_type(self, subject_type: str) -> None:
        self.state.subject_types.append((self.platform.platform_id, subject_type))

    async def issue_dpp(self, spec) -> DppResponse:
        dependencies = spec.dpp_payload.get("dependencies", [])
        self.state.published.append(
            PublishedRevision(
                platform_id=self.platform.platform_id,
                dpp_id=spec.dpp_id,
                dependency_count=len(dependencies),
                payload_entry_count=len(spec.dpp_payload),
            )
        )
        return DppResponse(
            dpp_id=spec.dpp_id,
            version=1,
            schema_version=spec.schema_version,
            dpp_payload=spec.dpp_payload,
            payload_hash="hash",
            created_at=datetime.now(UTC),
        )

    async def get_revision(self, dpp_id: str, version: int | None = None) -> DppResponse:
        raise AssertionError("duplicate DPP fallback was not expected")


def _timer(values: list[int]):
    iterator = iter(values)
    return lambda: next(iterator)


def _config(**overrides) -> ResolveFanoutConfig:
    values = {
        "factory_url": "http://factory",
        "fanout": 1,
        "depth": 2,
        "platform_count": 2,
        "samples": 1,
        "warmup": 0,
        "timeout_seconds": 30.0,
        "seed": "config",
        "verbose_errors": False,
    }
    values.update(overrides)
    return ResolveFanoutConfig(**values)


def test_default_max_resolved_depth_equals_generated_depth():
    assert effective_max_resolved_depth(_config(depth=4, max_resolved_depth=None)) == 4


def test_explicit_max_resolved_depth_is_accepted():
    assert effective_max_resolved_depth(_config(depth=4, max_resolved_depth=1)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("max_resolved_depth", [0, -1])
async def test_invalid_max_resolved_depth_is_rejected(max_resolved_depth: int):
    with pytest.raises(ValueError, match="max-resolved-depth must be >= 1"):
        await run_resolve_fanout_benchmark(_config(depth=4, max_resolved_depth=max_resolved_depth))


@pytest.mark.asyncio
async def test_invalid_payload_entries_is_rejected():
    with pytest.raises(ValueError, match="payload-entries must be >= 1"):
        await run_resolve_fanout_benchmark(_config(payload_entries=0))


@pytest.mark.asyncio
async def test_max_resolved_depth_above_generated_depth_is_rejected():
    with pytest.raises(ValueError, match="max-resolved-depth must not exceed depth"):
        await run_resolve_fanout_benchmark(_config(depth=2, max_resolved_depth=3))


@pytest.mark.asyncio
async def test_resolve_fanout_orchestration_small_tree():
    fed = FakeFederationClient(platform_count=2)
    resolver = FakeResolverClient("http://resolver")
    platform_state = FakePlatformState()
    progress_events: list[tuple[str, int]] = []
    config = ResolveFanoutConfig(
        factory_url="http://factory",
        fanout=1,
        depth=2,
        platform_count=2,
        samples=2,
        warmup=1,
        timeout_seconds=30.0,
        seed="small",
        verbose_errors=False,
        max_resolved_depth=2,
        payload_entries=3,
    )

    summary = await run_resolve_fanout_benchmark(
        config,
        federation_client=fed,
        resolver_client_factory=lambda url: resolver,
        platform_client_factory=lambda platform: FakePlatformClient(platform, platform_state),
        timer_ns=_timer([0, 10_000_000, 20_000_000, 40_000_000, 50_000_000, 80_000_000]),
        progress_callback=lambda description, advance: progress_events.append((description, advance)),
    )

    assert fed.created == []
    assert len(resolver.subject_types) == 2
    assert len(platform_state.published) == 3
    assert all(published.payload_entry_count == 3 for published in platform_state.published)
    assert "root" not in platform_state.published[0].dpp_id
    assert platform_state.published[-1].dpp_id.endswith("root")
    assert resolver.resolve_calls == 3
    assert [call[3] for call in resolver.closure_calls] == [2, 2, 2]
    assert summary.successful_calls == 2
    assert summary.errors == 0
    assert summary.median_ms == 25.0
    assert summary.max_resolved_depth == 2
    assert summary.payload_entries == 3
    assert sum(advance for _, advance in progress_events) == 11
    assert progress_events[-1] == ("Measured resolve calls 2/2", 1)


@pytest.mark.asyncio
async def test_resolve_fanout_creates_missing_platform():
    fed = FakeFederationClient(platform_count=2)
    resolver = FakeResolverClient("http://resolver")
    platform_state = FakePlatformState()
    config = ResolveFanoutConfig(
        factory_url="http://factory",
        fanout=2,
        depth=1,
        platform_count=3,
        samples=1,
        warmup=0,
        timeout_seconds=30.0,
        seed="grow",
        verbose_errors=False,
        max_resolved_depth=1,
    )

    summary = await run_resolve_fanout_benchmark(
        config,
        federation_client=fed,
        resolver_client_factory=lambda url: resolver,
        platform_client_factory=lambda platform: FakePlatformClient(platform, platform_state),
        timer_ns=_timer([0, 10_000_000]),
    )

    assert len(fed.created) == 1
    assert fed.created[0]["stack"] == "spring-postgres"
    assert fed.created[0]["issuer_id"] == "benchresolvegrowissuer2"
    assert resolver.subject_types[0] == "bench-resolve-grow-type-2"
    assert len(platform_state.published) == 3
    assert summary.created_platforms == 1
    assert summary.total_revisions == 3
    assert summary.successful_calls == 1
    assert resolver.closure_calls[0][3] == 1


@pytest.mark.asyncio
async def test_resolve_fanout_skips_old_hyphenated_benchmark_issuers():
    fed = FakeFederationClient(platform_count=2)
    fed.platforms.append(_bad_benchmark_platform(2))
    resolver = FakeResolverClient("http://resolver")
    platform_state = FakePlatformState()
    config = ResolveFanoutConfig(
        factory_url="http://factory",
        fanout=1,
        depth=1,
        platform_count=3,
        samples=1,
        warmup=0,
        timeout_seconds=30.0,
        seed="skip-bad",
        verbose_errors=False,
        max_resolved_depth=1,
    )

    summary = await run_resolve_fanout_benchmark(
        config,
        federation_client=fed,
        resolver_client_factory=lambda url: resolver,
        platform_client_factory=lambda platform: FakePlatformClient(platform, platform_state),
        timer_ns=_timer([0, 10_000_000]),
    )

    assert len(fed.created) == 1
    assert fed.created[0]["issuer_id"] == "benchresolveskipbadissuer2"
    assert all(published.platform_id != "platform-bad-2" for published in platform_state.published)
    assert summary.existing_platforms == 2
    assert summary.created_platforms == 1


@pytest.mark.asyncio
async def test_resolve_fanout_keeps_stats_when_measured_call_fails():
    fed = FakeFederationClient(platform_count=2)
    resolver = FakeResolverClient("http://resolver", fail_on_calls={2})
    platform_state = FakePlatformState()
    config = ResolveFanoutConfig(
        factory_url="http://factory",
        fanout=1,
        depth=1,
        platform_count=2,
        samples=2,
        warmup=0,
        timeout_seconds=30.0,
        seed="errors",
        verbose_errors=False,
        max_resolved_depth=1,
    )

    summary = await run_resolve_fanout_benchmark(
        config,
        federation_client=fed,
        resolver_client_factory=lambda url: resolver,
        platform_client_factory=lambda platform: FakePlatformClient(platform, platform_state),
        timer_ns=_timer([0, 10_000_000, 20_000_000]),
    )

    assert summary.successful_calls == 1
    assert summary.errors == 1
    assert summary.median_ms == 10.0
    assert summary.error_details[0].sample == 2
    assert "resolver exploded" in summary.error_details[0].message


@pytest.mark.asyncio
async def test_verbose_mode_groups_closure_resolution_calls(capsys):
    fed = FakeFederationClient(platform_count=2)
    resolver = FakeResolverClient("http://resolver")
    platform_state = FakePlatformState()
    config = _config(
        fanout=1,
        depth=1,
        platform_count=2,
        samples=1,
        warmup=0,
        seed="verbose",
        verbose=True,
        max_resolved_depth=1,
    )

    await run_resolve_fanout_benchmark(
        config,
        federation_client=fed,
        resolver_client_factory=lambda url: resolver,
        platform_client_factory=lambda platform: FakePlatformClient(platform, platform_state),
        timer_ns=_timer([0, 10_000_000]),
    )

    output = capsys.readouterr().out
    assert "=== closure sample 1/1" in output
    assert "max_depth=1" in output
    assert "=== closure sample 1/1 completed: 10.00 ms ===" in output
