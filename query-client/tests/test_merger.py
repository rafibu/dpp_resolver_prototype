from decimal import Decimal

from query_client.merger import merge_results
from query_client.models import (
    FederatedPredicateQueryRequest,
    PlatformCallStatus,
    PlatformQueryResponse,
    PlatformQueryResult,
)


def _request(**overrides):
    base = {"result_mode": "SELECT", "subject_type": "battery", "filters": []}
    base.update(overrides)
    return FederatedPredicateQueryRequest.model_validate(base)


def _result(platform_id, response, status=PlatformCallStatus.SUCCESS):
    return PlatformQueryResult(
        platform_id=platform_id,
        base_url=f"http://{platform_id}:8081",
        status=status,
        response=PlatformQueryResponse.model_validate(response) if response else None,
    )


def test_merge_select_combines_and_enriches_platform_id():
    request = _request(result_mode="SELECT")
    results = [
        _result(
            "p1",
            {
                "result_mode": "SELECT",
                "execution_mode": "INDEXED",
                "platform_id": "p1",
                "matches": [{"dpp_id": "a-1", "version": 1}],
            },
        ),
        _result(
            "p2",
            {
                "result_mode": "SELECT",
                "execution_mode": "INDEXED",
                "platform_id": "p2",
                "matches": [{"dpp_id": "b-1", "version": 2, "platform_id": "explicit"}],
            },
        ),
    ]
    combined = merge_results(request, results)
    assert combined.count == 2
    assert {m["platform_id"] for m in combined.matches} == {"p1", "explicit"}
    assert set(combined.source_platforms) == {"p1", "p2"}


def test_merge_select_deduplicates_on_identity():
    request = _request(result_mode="SELECT")
    match = {"dpp_id": "a-1", "version": 1}
    results = [
        _result(
            "p1",
            {
                "result_mode": "SELECT",
                "execution_mode": "INDEXED",
                "platform_id": "p1",
                "matches": [match, dict(match)],
            },
        )
    ]
    combined = merge_results(request, results)
    assert combined.count == 1


def test_merge_select_warns_when_no_identity():
    request = _request(result_mode="SELECT")
    results = [
        _result(
            "p1",
            {
                "result_mode": "SELECT",
                "execution_mode": "INDEXED",
                "platform_id": "p1",
                "matches": [{"name": "no-id"}, {"name": "no-id"}],
            },
        )
    ]
    combined = merge_results(request, results)
    assert combined.count == 2  # not deduplicated
    assert any("deduplicated" in w for w in combined.warnings)


def test_merge_count_sums():
    request = _request(result_mode="COUNT")
    results = [
        _result(
            "p1",
            {"result_mode": "COUNT", "execution_mode": "INDEXED", "platform_id": "p1", "count": 3},
        ),
        _result(
            "p2",
            {"result_mode": "COUNT", "execution_mode": "INDEXED", "platform_id": "p2", "count": 5},
        ),
    ]
    combined = merge_results(request, results)
    assert combined.count == 8


def test_merge_sum_uses_decimal():
    request = _request(result_mode="SUM", aggregate_path="mass_kg")
    results = [
        _result(
            "p1",
            {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "p1", "aggregate": "0.1"},
        ),
        _result(
            "p2",
            {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "p2", "aggregate": "0.2"},
        ),
    ]
    combined = merge_results(request, results)
    assert combined.aggregate == Decimal("0.3")


def test_merge_sum_missing_aggregate_with_empty_result_is_zero():
    request = _request(result_mode="SUM", aggregate_path="mass_kg")
    results = [
        _result(
            "p1",
            {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "p1", "aggregate": "5"},
        ),
        _result(
            "p2",
            {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "p2", "count": 0},
        ),
    ]
    combined = merge_results(request, results)
    assert combined.aggregate == Decimal("5")
    assert results[1].status is PlatformCallStatus.SUCCESS


def test_merge_sum_missing_aggregate_with_nonempty_result_fails_platform():
    request = _request(result_mode="SUM", aggregate_path="mass_kg")
    bad = _result(
        "p2",
        {
            "result_mode": "SUM",
            "execution_mode": "INDEXED",
            "platform_id": "p2",
            "count": 3,
        },
    )
    combined = merge_results(request, [bad])
    assert bad.status is PlatformCallStatus.FAILED
    assert combined.aggregate == Decimal("0")
    assert "p2" not in combined.source_platforms


def test_merge_only_includes_successful_platforms():
    request = _request(result_mode="COUNT")
    results = [
        _result(
            "p1",
            {"result_mode": "COUNT", "execution_mode": "INDEXED", "platform_id": "p1", "count": 3},
        ),
        _result("p2", None, status=PlatformCallStatus.FAILED),
    ]
    combined = merge_results(request, results)
    assert combined.count == 3
    assert combined.source_platforms == ["p1"]
