"""Tests for the run_query CLI logic (no network; run_federated_query patched)."""

import json
import pytest

import query_client.run_query as run_query
from query_client.models import (
    FederatedPredicateQueryRequest,
    FederatedQueryResultResponse,
    JobStatus,
)
from query_client.validation import QueryValidationError


def _result(status: JobStatus, **extra) -> FederatedQueryResultResponse:
    from datetime import datetime, timezone

    base = {
        "job_id": "job-1",
        "status": status,
        "query": FederatedPredicateQueryRequest.model_validate(
            {"result_mode": "COUNT", "subject_types": ["battery"]}
        ),
        "timeout_ms": 1000,
        "created_at": datetime.now(timezone.utc),
        "total_platforms": 1,
        "completed_platforms": 1,
        "successful_platforms": 1,
        "failed_platforms": 0,
        "timed_out_platforms": 0,
        "complete": True,
        "platform_results": [],
    }
    base.update(extra)
    return FederatedQueryResultResponse.model_validate(base)


def _write_request(tmp_path, payload) -> str:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_cli_prints_result_json_and_exits_zero(tmp_path, capsys, monkeypatch):
    captured_request = {}

    async def fake(request, config=None):
        captured_request["value"] = request
        return _result(JobStatus.SUCCESS)

    monkeypatch.setattr(run_query, "run_federated_query", fake)
    request_path = _write_request(tmp_path, {"result_mode": "COUNT", "subject_types": ["battery"]})

    exit_code = run_query.main(["--request", request_path])
    assert exit_code == 0

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["status"] == "SUCCESS"
    assert parsed["job_id"] == "job-1"
    # The loaded request was parsed into the model and forwarded.
    assert isinstance(captured_request["value"], FederatedPredicateQueryRequest)
    assert captured_request["value"].subject_type == "battery"


def test_cli_partial_exits_zero(tmp_path, capsys, monkeypatch):
    async def fake(request, config=None):
        return _result(JobStatus.PARTIAL, complete=False, failed_platforms=1)

    monkeypatch.setattr(run_query, "run_federated_query", fake)
    request_path = _write_request(tmp_path, {"result_mode": "COUNT", "subject_types": ["battery"]})
    assert run_query.main(["--request", request_path]) == 0


def test_cli_failed_exits_one(tmp_path, capsys, monkeypatch):
    async def fake(request, config=None):
        return _result(JobStatus.FAILED, complete=False, successful_platforms=0, failed_platforms=1)

    monkeypatch.setattr(run_query, "run_federated_query", fake)
    request_path = _write_request(tmp_path, {"result_mode": "COUNT", "subject_types": ["battery"]})
    assert run_query.main(["--request", request_path]) == 1


def test_cli_validation_error_exits_two(tmp_path, capsys, monkeypatch):
    async def fake(request, config=None):
        raise QueryValidationError("aggregate_path is required for result_mode SUM")

    monkeypatch.setattr(run_query, "run_federated_query", fake)
    request_path = _write_request(tmp_path, {"result_mode": "SUM", "subject_types": ["battery"]})
    assert run_query.main(["--request", request_path]) == 2
    err = capsys.readouterr().err
    assert "Invalid query request" in err


def test_cli_malformed_request_raises(tmp_path, monkeypatch):
    async def fake(request, config=None):  # pragma: no cover - should not be reached
        return _result(JobStatus.SUCCESS)

    monkeypatch.setattr(run_query, "run_federated_query", fake)
    # Unknown result_mode fails pydantic validation before the query runs.
    request_path = _write_request(tmp_path, {"result_mode": "WRONG", "subject_types": ["battery"]})
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        run_query.main(["--request", request_path])
