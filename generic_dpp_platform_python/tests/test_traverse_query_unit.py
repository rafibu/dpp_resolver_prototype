from __future__ import annotations

import pytest
from generic_dpp_platform.queries.index import project_payload_to_references
from generic_dpp_platform.queries.models import (
    QueryExecutionMode,
    TraverseQueryRequest,
    TraverseQueryResponse,
)
from generic_dpp_platform.queries.router import _parse_traverse_request
from generic_dpp_platform.queries.service import (
    _document_contains_matching_reference,
    _reference_matches,
    validate_traverse_request,
)
from pydantic import ValidationError
from starlette.requests import Request


def _request(**overrides) -> TraverseQueryRequest:
    values = {
        "subject_type": "component",
        "dpp_id": "issuer-component-1",
        "sources": [{"subject_type": "pv_module"}],
    }
    values.update(overrides)
    return TraverseQueryRequest.model_validate(values)


def _http_request(query: bytes) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/query/traverse",
            "query_string": query,
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


def test_flattened_java_request_parses_camel_case_scopes_and_defaults_mode() -> None:
    request = _parse_traverse_request(
        _http_request(
            b"subjectType=component&dppId=issuer-component-1"
            b"&revisionNumber=3&sources[0].subjectType=pv_module"
            b"&sources[0].referencePaths[0]=components.primary_component"
        )
    )

    assert request.execution_mode is QueryExecutionMode.INDEXED
    assert request.revision_number == 3
    assert request.sources[0].subject_type == "pv_module"
    assert request.sources[0].reference_paths == ["components.primary_component"]


def test_traverse_dto_validation_and_java_wire_values() -> None:
    request = _request(execution_mode="ON_DEMAND")

    assert request.model_dump(mode="json") == {
        "subject_type": "component",
        "dpp_id": "issuer-component-1",
        "execution_mode": "ON_DEMAND",
        "revision_number": None,
        "sources": [{"subject_type": "pv_module", "reference_paths": None}],
    }
    assert TraverseQueryResponse(
        platform_id="issuer",
        subject_type="component",
        dpp_id="issuer-component-1",
        matches=[],
    ).model_dump(mode="json") == {
        "platform_id": "issuer",
        "subject_type": "component",
        "dpp_id": "issuer-component-1",
        "matches": [],
    }
    with pytest.raises(ValidationError):
        TraverseQueryRequest.model_validate({"subject_type": "component", "dpp_id": "id"})
    with pytest.raises(ValueError, match="subject_type is required"):
        validate_traverse_request(_request(subject_type=" "))


def test_reference_materialization_and_matching_cover_hard_and_logical_targets() -> None:
    payload = {
        "components": {
            "primary_component": {"$ref": "component/issuer-component-1/3"},
            "logical_component": {"$ref": "component/issuer-component-1"},
        }
    }
    references = project_payload_to_references(payload, "issuer-module-1", "pv_module")
    by_path = {reference["reference_path"]: reference for reference in references}

    assert by_path["components.primary_component"]["reference_type"] == "HARD"
    assert by_path["components.primary_component"]["target_revision_number"] == 3
    assert by_path["components.logical_component"]["reference_type"] == "SOFT"
    assert _reference_matches(
        {"$ref": "component/issuer-component-1/3"},
        _request(revision_number=3),
    )
    assert not _reference_matches(
        {"$ref": "component/issuer-component-1"},
        _request(revision_number=3),
    )
    assert _reference_matches(
        {"$ref": "component/issuer-component-1"},
        _request(),
    )


def test_source_scope_path_filter_and_recursive_on_demand_matching() -> None:
    document = {
        "components": {
            "primary_component": {"$ref": "component/issuer-component-1/3"},
            "other": {"$ref": "component/issuer-component-1/3"},
        }
    }
    exact_request = _request(
        revision_number=3,
        sources=[{"subject_type": "pv_module", "reference_paths": ["components.primary_component"]}],
    )
    wrong_path_request = _request(
        revision_number=3,
        sources=[{"subject_type": "pv_module", "reference_paths": ["components.absent"]}],
    )

    assert _document_contains_matching_reference(document, exact_request.sources[0], exact_request)
    assert not _document_contains_matching_reference(document, wrong_path_request.sources[0], wrong_path_request)
