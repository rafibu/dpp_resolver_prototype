"""Tests that pin the generic platform's GET query-parameter contract."""

import pytest

from query_client.config import Config
from query_client.models import FederatedPredicateQueryRequest
from support import (
    json_handler,
    make_service,
    make_transport,
    resolver_handler,
    select_payload,
    sum_payload,
)


@pytest.mark.asyncio
async def test_forwarded_request_uses_flattened_get_params_without_timeout():
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(select_payload("platform-a", [])),
            "platform-b": json_handler(select_payload("platform-b", [])),
        }
    )
    service = make_service(transport)
    request = FederatedPredicateQueryRequest.model_validate(
        {
            "result_mode": "SELECT",
            "execution_mode": "ON_DEMAND",
            "subject_type": "battery",
            "return_fields": ["status"],
            "timeout_ms": 7000,
            "filters": [
                {"path": "status", "operator": "EQ", "value": "active"},
                {"path": "color", "operator": "IN", "value": ["red", "blue"]},
            ],
        }
    )
    await service.run_to_completion(request)
    await service.aclose()

    params = transport.params_for("platform-a")
    assert params == [
        ("resultMode", "SELECT"),
        ("executionMode", "ON_DEMAND"),
        ("subjectType", "battery"),
        ("filters[0].path", "status"),
        ("filters[0].operator", "EQ"),
        ("filters[0].value", "active"),
        ("filters[1].path", "color"),
        ("filters[1].operator", "IN"),
        ("filters[1].value", "red"),
        ("filters[1].value", "blue"),
        ("returnFields", "status"),
    ]
    assert transport.params_for("platform-b") == params


@pytest.mark.asyncio
async def test_request_method_path_and_content_type():
    config = Config(
        resolver_base_url="http://localhost:8080",
        platform_query_path="/query/predicate",
        platform_query_method="GET",
    )
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(select_payload("platform-a", [])),
            "platform-b": json_handler(select_payload("platform-b", [])),
        }
    )
    service = make_service(transport, config=config)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_type": "battery"}
    )
    await service.run_to_completion(request)
    await service.aclose()

    platform_reqs = transport.platform_requests()
    assert len(platform_reqs) == 2
    for req in platform_reqs:
        assert req.method == "GET"
        assert req.url.path == "/query/predicate"
        assert req.url.params["resultMode"] == "SELECT"


@pytest.mark.asyncio
async def test_sum_forwards_aggregate_path_only():
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(sum_payload("platform-a", "1")),
            "platform-b": json_handler(sum_payload("platform-b", "2")),
        }
    )
    service = make_service(transport)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SUM", "subject_type": "battery", "aggregate_path": "material.mass_kg"}
    )
    await service.run_to_completion(request)
    await service.aclose()

    params = transport.params_for("platform-a")
    assert ("aggregatePath", "material.mass_kg") in params
    assert not any(key == "returnFields" for key, _ in params)


@pytest.mark.asyncio
async def test_configurable_path_is_used():
    config = Config(
        resolver_base_url="http://localhost:8080",
        platform_query_path="/api/v1/query/predicate",
    )
    transport = make_transport(
        {
            "resolver": resolver_handler(),
            "platform-a": json_handler(select_payload("platform-a", [])),
            "platform-b": json_handler(select_payload("platform-b", [])),
        }
    )
    service = make_service(transport, config=config)
    request = FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "SELECT", "subject_type": "battery"}
    )
    await service.run_to_completion(request)
    await service.aclose()
    assert all(r.url.path == "/api/v1/query/predicate" for r in transport.platform_requests())
