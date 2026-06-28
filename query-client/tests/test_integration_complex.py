"""Complex, realistic multi-platform orchestration scenarios."""

import httpx
import pytest
from decimal import Decimal

from query_client.models import (
    FederatedPredicateQueryRequest,
    JobStatus,
    PlatformCallStatus,
)
from support import (
    count_payload,
    error_handler,
    json_handler,
    make_service,
    make_transport,
    resolver_handler,
    select_payload,
    sum_payload,
)

FOUR_PLATFORMS = [
    {"platform": "platform-a", "issuer_id": "A", "resolution_url": "http://platform-a:8081/dpps/{dppId}"},
    {"platform": "platform-b", "issuer_id": "B", "resolution_url": "http://platform-b:8082/dpps/{dppId}"},
    {"platform": "platform-c", "issuer_id": "C", "resolution_url": "http://platform-c:8083/dpps/{dppId}"},
    {"platform": "platform-d", "issuer_id": "D", "resolution_url": "http://platform-d:8084/dpps/{dppId}"},
]


def _request(**overrides):
    base = {"result_mode": "SELECT", "subject_types": ["battery"]}
    base.update(overrides)
    return FederatedPredicateQueryRequest.model_validate(base)


@pytest.mark.asyncio
async def test_select_mixed_success_failure_timeout_and_bad_shape():
    # a: ok with an in-platform duplicate; b: ok; c: HTTP 500; d: too slow -> timeout.
    dup = {"dpp_id": "a-1", "version": 1}
    transport = make_transport(
        {
            "resolver": resolver_handler(FOUR_PLATFORMS),
            "platform-a": json_handler(
                select_payload("platform-a", [dup, dict(dup), {"dpp_id": "a-2", "version": 3}])
            ),
            "platform-b": json_handler(select_payload("platform-b", [{"dpp_id": "b-1", "version": 1}])),
            "platform-c": json_handler({"error": "boom"}, status=500),
            "platform-d": json_handler(select_payload("platform-d", []), delay=2.0),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request(timeout_ms=250))
    await service.aclose()

    assert result.status is JobStatus.PARTIAL
    assert result.complete is False
    assert result.total_platforms == 4
    assert result.successful_platforms == 2
    assert result.failed_platforms == 1
    assert result.timed_out_platforms == 1
    assert result.completed_platforms == 4

    by_id = {r.platform_id: r for r in result.platform_results}
    assert by_id["platform-c"].status is PlatformCallStatus.FAILED
    assert by_id["platform-c"].http_status == 500
    assert by_id["platform-d"].status is PlatformCallStatus.TIMEOUT
    assert by_id["platform-d"].error_message

    # a's in-platform duplicate is collapsed -> a contributes 2, b contributes 1.
    combined = result.combined_result
    assert combined.count == 3
    assert sorted(combined.source_platforms) == ["platform-a", "platform-b"]
    for match in combined.matches:
        assert "platform_id" in match


@pytest.mark.asyncio
async def test_cross_platform_same_identity_not_deduplicated():
    # Same dpp_id/version reported by two different platforms must both survive,
    # because the dedup key includes platform_id.
    shared = {"dpp_id": "shared-1", "version": 2}
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(select_payload("platform-a", [dict(shared)])),
            "platform-b": json_handler(select_payload("platform-b", [dict(shared)])),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request())
    await service.aclose()
    assert result.combined_result.count == 2
    assert {m["platform_id"] for m in result.combined_result.matches} == {"platform-a", "platform-b"}


@pytest.mark.asyncio
async def test_count_partial_with_failure():
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(count_payload("platform-a", 7)),
            "platform-b": json_handler({"boom": True}, status=503),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request(result_mode="COUNT"))
    await service.aclose()
    assert result.status is JobStatus.PARTIAL
    assert result.combined_result.count == 7  # partial count from the one success
    assert result.complete is False


@pytest.mark.asyncio
async def test_sum_demotes_platform_missing_aggregate_on_nonempty_result():
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(sum_payload("platform-a", "12.5")),
            # Non-empty result but no aggregate -> invalid -> demoted to FAILED.
            "platform-b": json_handler(
                {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "platform-b", "count": 4}
            ),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request(result_mode="SUM", aggregate_path="mass_kg"))
    await service.aclose()

    assert result.status is JobStatus.PARTIAL
    assert result.successful_platforms == 1
    assert result.failed_platforms == 1
    assert Decimal(str(result.combined_result.aggregate)) == Decimal("12.5")
    assert "platform-b" not in result.combined_result.source_platforms


@pytest.mark.asyncio
async def test_all_timeout_yields_timeout_status():
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(select_payload("platform-a", []), delay=2.0),
            "platform-b": json_handler(select_payload("platform-b", []), delay=2.0),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request(timeout_ms=150))
    await service.aclose()
    assert result.status is JobStatus.TIMEOUT
    assert result.timed_out_platforms == 2
    assert result.successful_platforms == 0


@pytest.mark.asyncio
async def test_connection_error_is_failed_not_fatal():
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(count_payload("platform-a", 5)),
            "platform-b": error_handler(httpx.ConnectError("refused")),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request(result_mode="COUNT"))
    await service.aclose()
    assert result.status is JobStatus.PARTIAL
    assert result.failed_platforms == 1
    assert result.combined_result.count == 5


@pytest.mark.asyncio
async def test_no_registered_platforms_is_successful_empty_result():
    transport = make_transport({"resolver": resolver_handler([])})
    service = make_service(transport)
    result = await service.run_to_completion(_request(result_mode="COUNT"))
    await service.aclose()
    assert result.status is JobStatus.SUCCESS
    assert result.complete is True
    assert result.total_platforms == 0
    assert result.combined_result.count == 0


@pytest.mark.asyncio
async def test_deduplicated_platforms_queried_once_each():
    duplicated = [
        {"platform": "platform-a", "issuer_id": "A", "resolution_url": "http://platform-a:8081/dpps/{dppId}"},
        {"platform": "platform-a", "issuer_id": "A2", "resolution_url": "http://platform-a:8081/dpps/{dppId}"},
        {"platform": "platform-b", "issuer_id": "B", "resolution_url": "http://platform-b:8082/dpps/{dppId}"},
    ]
    transport = make_transport(
        {
            "resolver": resolver_handler(duplicated),
            "platform-a": json_handler(count_payload("platform-a", 2)),
            "platform-b": json_handler(count_payload("platform-b", 3)),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request(result_mode="COUNT"))
    await service.aclose()

    assert result.total_platforms == 2
    assert result.combined_result.count == 5
    # platform-a contacted exactly once despite two issuer mappings.
    hosts = [r.url.host for r in transport.platform_requests()]
    assert hosts.count("platform-a") == 1
    assert hosts.count("platform-b") == 1


@pytest.mark.asyncio
async def test_per_platform_durations_recorded():
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(count_payload("platform-a", 1), delay=0.05),
            "platform-b": json_handler(count_payload("platform-b", 1), delay=0.05),
        }
    )
    service = make_service(transport)
    result = await service.run_to_completion(_request(result_mode="COUNT"))
    await service.aclose()
    for r in result.platform_results:
        assert r.duration_ms is not None
        assert r.duration_ms >= 40  # at least the injected delay
        assert r.started_at is not None and r.finished_at is not None
