"""Tests that pin the platform-local request contract actually sent on the wire.

These assert the acceptance criterion "the platform-local query request uses
snake_case JSON fields", plus method/path/headers and the timeout exclusion.
"""

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
async def test_forwarded_body_is_snake_case_json_without_timeout():
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

    body = transport.body_for("platform-a")
    assert body == {
        "result_mode": "SELECT",
        "execution_mode": "ON_DEMAND",
        "subject_type": "battery",
        "filters": [
            {"path": "status", "operator": "EQ", "value": "active"},
            {"path": "color", "operator": "IN", "value": ["red", "blue"]},
        ],
        "return_fields": ["status"],
    }
    assert "timeout_ms" not in body
    assert "aggregate_path" not in body

    # Both platforms received the identical body.
    assert transport.body_for("platform-b") == body


@pytest.mark.asyncio
async def test_request_method_path_and_content_type():
    config = Config(
        resolver_base_url="http://localhost:8080",
        platform_query_path="/query/predicate",
        platform_query_method="POST",
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
        assert req.method == "POST"
        assert req.url.path == "/query/predicate"
        assert req.headers["content-type"].startswith("application/json")


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

    body = transport.body_for("platform-a")
    assert body["aggregate_path"] == "material.mass_kg"
    assert "return_fields" not in body


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
