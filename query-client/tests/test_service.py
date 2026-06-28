"""End-to-end orchestration tests using a routing mock transport.

A custom async transport lets us simulate per-platform success, HTTP errors, and
slow responses (for federation timeouts) without a real network.
"""

import asyncio
import httpx
import pytest

from query_client.config import Config
from query_client.models import (
    FederatedPredicateQueryRequest,
    JobStatus,
    PlatformCallStatus,
)
from query_client.service import FederatedQueryService

RESOLVER_PLATFORMS = [
    {"platform": "platform-a", "issuer_id": "A", "resolution_url": "http://platform-a:8081/dpps/{dppId}"},
    {"platform": "platform-b", "issuer_id": "B", "resolution_url": "http://platform-b:8082/dpps/{dppId}"},
]


class RoutingTransport(httpx.AsyncBaseTransport):
    """Dispatches requests to per-host handlers; supports async delays."""

    def __init__(self, handlers):
        self._handlers = handlers

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = request.url.host
        if request.url.path == "/admin/platforms":
            key = "resolver"
        handler = self._handlers[key]
        return await handler(request)


def _config():
    return Config(resolver_base_url="http://localhost:8080")


def _resolver_ok(request):
    async def _h(_req):
        return httpx.Response(200, json=RESOLVER_PLATFORMS)
    return _h


def _platform_response(payload, *, status=200, delay=0.0):
    async def _h(_req):
        if delay:
            await asyncio.sleep(delay)
        return httpx.Response(status, json=payload)
    return _h


def _service_with(handlers, config=None):
    transport = RoutingTransport(handlers)
    client = httpx.AsyncClient(transport=transport)
    return FederatedQueryService(config=config or _config(), http_client=client)


def _select_payload(platform_id, matches):
    return {
        "result_mode": "SELECT",
        "execution_mode": "INDEXED",
        "platform_id": platform_id,
        "matches": matches,
    }


@pytest.mark.asyncio
async def test_select_full_flow():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response(_select_payload("platform-a", [{"dpp_id": "a-1", "version": 1}])),
        "platform-b": _platform_response(_select_payload("platform-b", [{"dpp_id": "b-1", "version": 1}])),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_types": ["battery"], "filters": []}
    )
    result = await service.run_to_completion(request)
    await service.aclose()

    assert result.status is JobStatus.SUCCESS
    assert result.complete is True
    assert result.total_platforms == 2
    assert result.successful_platforms == 2
    assert result.combined_result.count == 2
    assert {m["platform_id"] for m in result.combined_result.matches} == {"platform-a", "platform-b"}
    for pr in result.platform_results:
        assert pr.status is PlatformCallStatus.SUCCESS
        assert pr.duration_ms is not None and pr.duration_ms >= 0


@pytest.mark.asyncio
async def test_count_sums_across_platforms():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response(
            {"result_mode": "COUNT", "execution_mode": "INDEXED", "platform_id": "platform-a", "count": 4}
        ),
        "platform-b": _platform_response(
            {"result_mode": "COUNT", "execution_mode": "INDEXED", "platform_id": "platform-b", "count": 6}
        ),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "COUNT", "subject_types": ["battery"]}
    )
    result = await service.run_to_completion(request)
    await service.aclose()
    assert result.status is JobStatus.SUCCESS
    assert result.combined_result.count == 10


@pytest.mark.asyncio
async def test_sum_aggregates_with_decimal():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response(
            {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "platform-a", "aggregate": "0.1"}
        ),
        "platform-b": _platform_response(
            {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "platform-b", "aggregate": "0.2"}
        ),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SUM", "subject_types": ["battery"], "aggregate_path": "mass_kg"}
    )
    result = await service.run_to_completion(request)
    await service.aclose()
    assert result.status is JobStatus.SUCCESS
    assert float(result.combined_result.aggregate) == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_partial_when_one_platform_fails():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response(_select_payload("platform-a", [{"dpp_id": "a-1", "version": 1}])),
        "platform-b": _platform_response({"error": "boom"}, status=500),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_types": ["battery"]}
    )
    result = await service.run_to_completion(request)
    await service.aclose()

    assert result.status is JobStatus.PARTIAL
    assert result.complete is False
    assert result.successful_platforms == 1
    assert result.failed_platforms == 1
    failed = [r for r in result.platform_results if r.status is PlatformCallStatus.FAILED]
    assert failed and failed[0].http_status == 500


@pytest.mark.asyncio
async def test_timeout_marks_slow_platform():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response(_select_payload("platform-a", [{"dpp_id": "a-1", "version": 1}])),
        "platform-b": _platform_response(_select_payload("platform-b", []), delay=2.0),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_types": ["battery"], "timeout_ms": 200}
    )
    result = await service.run_to_completion(request)
    await service.aclose()

    assert result.status is JobStatus.PARTIAL
    assert result.timed_out_platforms == 1
    assert result.successful_platforms == 1
    timed = [r for r in result.platform_results if r.status is PlatformCallStatus.TIMEOUT]
    assert timed and timed[0].platform_id == "platform-b"


@pytest.mark.asyncio
async def test_failed_when_all_platforms_fail():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response({"error": "boom"}, status=500),
        "platform-b": _platform_response({"error": "boom"}, status=500),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "COUNT", "subject_types": ["battery"]}
    )
    result = await service.run_to_completion(request)
    await service.aclose()
    assert result.status is JobStatus.FAILED
    assert result.successful_platforms == 0


@pytest.mark.asyncio
async def test_invalid_platform_shape_is_failed_not_fatal():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response(_select_payload("platform-a", [{"dpp_id": "a-1", "version": 1}])),
        "platform-b": _platform_response({"unexpected": "shape"}),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_types": ["battery"]}
    )
    result = await service.run_to_completion(request)
    await service.aclose()
    assert result.status is JobStatus.PARTIAL
    assert result.failed_platforms == 1


@pytest.mark.asyncio
async def test_background_start_and_poll():
    handlers = {
        "resolver": _resolver_ok(None),
        "platform-a": _platform_response(_select_payload("platform-a", []), delay=0.05),
        "platform-b": _platform_response(_select_payload("platform-b", []), delay=0.05),
    }
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_types": ["battery"]}
    )
    job = await service.start(request)
    assert job.status in (JobStatus.PENDING, JobStatus.RUNNING)

    for _ in range(100):
        current = await service.store.get_job(job.job_id)
        if current.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            break
        await asyncio.sleep(0.02)
    await service.aclose()

    final = await service.store.get_job(job.job_id)
    assert final.status is JobStatus.SUCCESS


@pytest.mark.asyncio
async def test_resolver_failure_marks_job_failed():
    async def _bad_resolver(_req):
        return httpx.Response(500, json={"error": "down"})

    handlers = {"resolver": _bad_resolver}
    service = _service_with(handlers)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "COUNT", "subject_types": ["battery"]}
    )
    result = await service.run_to_completion(request)
    await service.aclose()
    assert result.status is JobStatus.FAILED
    assert result.error is not None
    assert result.combined_result.warnings
