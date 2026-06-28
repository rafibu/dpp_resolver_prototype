import pytest

from query_client.models import FederatedPredicateQueryRequest
from query_client.validation import QueryValidationError, validate_request


def _request(**overrides):
    base = {
        "result_mode": "SELECT",
        "subject_types": ["battery"],
        "filters": [],
    }
    base.update(overrides)
    return FederatedPredicateQueryRequest.model_validate(base)


def test_execution_mode_defaults_to_indexed():
    request = _request()
    assert request.execution_mode.value == "INDEXED"


def test_select_with_filters_is_valid():
    request = _request(
        filters=[{"path": "status", "operator": "EQ", "value": "active"}]
    )
    validate_request(request)  # no raise


def test_empty_filters_is_valid():
    validate_request(_request(result_mode="COUNT"))


def test_return_fields_rejected_for_count():
    request = _request(result_mode="COUNT", return_fields=["a", "b"])
    with pytest.raises(QueryValidationError):
        validate_request(request)


def test_aggregate_path_required_for_sum():
    request = _request(result_mode="SUM")
    with pytest.raises(QueryValidationError):
        validate_request(request)


def test_aggregate_path_forbidden_for_select():
    request = _request(result_mode="SELECT", aggregate_path="x.y")
    with pytest.raises(QueryValidationError):
        validate_request(request)


def test_sum_with_aggregate_path_is_valid():
    validate_request(_request(result_mode="SUM", aggregate_path="mass_kg"))


def test_exists_with_value_is_rejected():
    request = _request(
        filters=[{"path": "x", "operator": "EXISTS", "value": "y"}]
    )
    with pytest.raises(QueryValidationError):
        validate_request(request)


def test_exists_without_value_is_valid():
    validate_request(_request(filters=[{"path": "x", "operator": "EXISTS"}]))


def test_in_requires_non_empty_array():
    with pytest.raises(QueryValidationError):
        validate_request(_request(filters=[{"path": "x", "operator": "IN", "value": []}]))
    with pytest.raises(QueryValidationError):
        validate_request(
            _request(filters=[{"path": "x", "operator": "IN", "value": "scalar"}])
        )


def test_in_with_array_is_valid():
    validate_request(
        _request(filters=[{"path": "x", "operator": "IN", "value": [1, 2, 3]}])
    )


def test_gt_requires_numeric_value():
    with pytest.raises(QueryValidationError):
        validate_request(_request(filters=[{"path": "x", "operator": "GT", "value": "abc"}]))
    # numeric string is accepted
    validate_request(_request(filters=[{"path": "x", "operator": "GT", "value": "12.5"}]))
    validate_request(_request(filters=[{"path": "x", "operator": "GT", "value": 5}]))
    validate_request(_request(filters=[{"path": "manufacturing.date", "operator": "GTE", "value": "2024-01-01"}]))


def test_gt_rejects_boolean_value():
    with pytest.raises(QueryValidationError):
        validate_request(_request(filters=[{"path": "x", "operator": "GT", "value": True}]))


def test_eq_requires_scalar():
    with pytest.raises(QueryValidationError):
        validate_request(_request(filters=[{"path": "x", "operator": "EQ", "value": [1]}]))
    with pytest.raises(QueryValidationError):
        validate_request(_request(filters=[{"path": "x", "operator": "EQ"}]))


def test_unknown_operator_rejected_by_pydantic():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        _request(filters=[{"path": "x", "operator": "BETWEEN", "value": [1, 2]}])
    with pytest.raises(pydantic.ValidationError):
        _request(filters=[{"path": "x", "operator": "CONTAINS", "value": "a"}])


def test_subject_types_are_optional_but_not_blank():
    validate_request(_request(subject_types=[]))
    validate_request(_request(subject_types=None))
    with pytest.raises(QueryValidationError):
        validate_request(_request(subject_types=["battery", " "]))
