"""Unit tests for model behavior: forwarded body, serialization, projections."""

import json
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from query_client.models import (
    CombinedQueryResult,
    FederatedPredicateQueryRequest,
    FederatedQueryJob,
    JobStatus,
    PlatformCallStatus,
    PlatformQueryResponse,
    PlatformQueryResult,
    QueryExecutionMode,
    QueryResultMode,
)


def _request(**overrides):
    base = {"result_mode": "SELECT", "subject_types": ["battery"]}
    base.update(overrides)
    return FederatedPredicateQueryRequest.model_validate(base)


def test_to_platform_body_excludes_timeout_and_keeps_snake_case():
    request = _request(
        result_mode="SELECT",
        execution_mode="ON_DEMAND",
        return_fields=["status", "mass_kg"],
        timeout_ms=5000,
        filters=[
            {"path": "status", "operator": "EQ", "value": "active"},
            {"path": "mass_kg", "operator": "GT", "value": 10},
            {"path": "color", "operator": "IN", "value": ["red", "blue"]},
        ],
    )
    body = request.to_platform_body()

    assert set(body) == {"result_mode", "execution_mode", "subject_types", "filters", "return_fields"}
    assert "timeout_ms" not in body
    assert "aggregate_path" not in body  # not a SUM query
    assert body["result_mode"] == "SELECT"
    assert body["execution_mode"] == "ON_DEMAND"
    assert body["subject_types"] == ["battery"]
    assert body["return_fields"] == ["status", "mass_kg"]
    assert body["filters"][1] == {"path": "mass_kg", "operator": "GT", "value": 10}
    assert body["filters"][2]["value"] == ["red", "blue"]
    # Must be JSON-serializable with enum *values* (strings), not Enum members.
    encoded = json.dumps(body)
    assert "QueryResultMode" not in encoded


def test_to_platform_body_includes_aggregate_path_for_sum():
    body = _request(result_mode="SUM", aggregate_path="material.mass_kg").to_platform_body()
    assert body["aggregate_path"] == "material.mass_kg"
    assert "return_fields" not in body


def test_to_platform_body_defaults_execution_mode_indexed():
    body = _request().to_platform_body()
    assert body["execution_mode"] == "INDEXED"
    assert body["filters"] == []


def test_to_platform_body_omits_empty_subject_types_for_all_type_query():
    body = _request(subject_types=[]).to_platform_body()
    assert "subject_types" not in body


def test_legacy_subject_type_input_is_accepted_but_not_emitted():
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_type": "battery"}
    )
    assert request.subject_types == ["battery"]
    assert request.subject_type == "battery"
    assert request.to_platform_body()["subject_types"] == ["battery"]


def test_platform_response_preserves_unknown_fields():
    response = PlatformQueryResponse.model_validate(
        {
            "result_mode": "SELECT",
            "execution_mode": "INDEXED",
            "platform_id": "p1",
            "matches": [{"dpp_id": "x-1", "version": 1}],
            "took_ms": 42,
            "extra_block": {"a": 1},
        }
    )
    dumped = response.model_dump()
    assert dumped["took_ms"] == 42
    assert dumped["extra_block"] == {"a": 1}


def test_aggregate_serializes_to_json_number():
    response = PlatformQueryResponse.model_validate(
        {"result_mode": "SUM", "execution_mode": "INDEXED", "platform_id": "p1", "aggregate": "1.5"}
    )
    assert response.aggregate == Decimal("1.5")
    as_json = json.loads(response.model_dump_json())
    assert as_json["aggregate"] == 1.5
    assert isinstance(as_json["aggregate"], float)


def test_combined_result_aggregate_serializes_to_number():
    combined = CombinedQueryResult(
        result_mode=QueryResultMode.SUM,
        execution_mode=QueryExecutionMode.INDEXED,
        aggregate=Decimal("0.30"),
    )
    assert json.loads(combined.model_dump_json())["aggregate"] == 0.30


def _job():
    created = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
    return FederatedQueryJob(
        job_id="job-1",
        query=_request(),
        timeout_ms=120000,
        created_at=created,
    )


def test_duration_ms_none_before_start_then_computed():
    job = _job()
    assert job.duration_ms is None
    job.started_at = job.created_at
    job.finished_at = job.created_at + timedelta(milliseconds=250)
    assert job.duration_ms == 250


def test_start_response_builds_status_and_result_urls():
    job = _job()
    start = job.to_start_response()
    assert start.status_url == "/api/v1/federated-queries/job-1"
    assert start.result_url == "/api/v1/federated-queries/job-1/result"
    assert start.status is JobStatus.PENDING


def test_status_and_result_projections_carry_counts():
    job = _job()
    job.total_platforms = 3
    job.successful_platforms = 2
    job.failed_platforms = 1
    job.platform_results = [
        PlatformQueryResult(platform_id="p1", base_url="http://p1", status=PlatformCallStatus.SUCCESS)
    ]
    status = job.to_status_response()
    result = job.to_result_response()
    assert status.total_platforms == 3
    assert status.successful_platforms == 2
    assert result.failed_platforms == 1
    assert result.query.subject_type == "battery"


def test_request_rejects_unknown_operator():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        _request(filters=[{"path": "x", "operator": "BETWEEN", "value": [1, 2]}])
