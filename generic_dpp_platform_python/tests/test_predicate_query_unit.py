from __future__ import annotations

import pytest
from generic_dpp_platform.queries.helpers import matches_filter, select_fields
from generic_dpp_platform.queries.index import project_payload_to_facts, validate_fact_document
from generic_dpp_platform.queries.models import (
    PredicateFilter,
    PredicateOperator,
    PredicateQueryRequest,
    QueryExecutionMode,
    QueryResultMode,
)
from generic_dpp_platform.queries.service import (
    IndexedQueryMatcher,
    OnDemandQueryMatcher,
    empty_response,
    validate_request,
)
from pydantic import ValidationError
from typing import Any


def _request(**overrides: Any) -> PredicateQueryRequest:
    values: dict[str, Any] = {
        "result_mode": QueryResultMode.SELECT,
        "execution_mode": QueryExecutionMode.INDEXED,
        "subject_types": ["Battery"],
    }
    values.update(overrides)
    return PredicateQueryRequest(**values)


def _fact(logical_dpp_id: str, path: str, **value: Any) -> dict[str, Any]:
    return {
        "logical_dpp_id": logical_dpp_id,
        "subject_type": "Battery",
        "path": path,
        **value,
    }


def test_enums_parse_and_serialize_as_java_wire_values() -> None:
    request = PredicateQueryRequest.model_validate(
        {
            "result_mode": "COUNT",
            "execution_mode": "ON_DEMAND",
            "subject_types": ["Battery"],
            "filters": [{"path": "chemistry", "operator": "EQ", "value": "NMC"}],
        }
    )

    assert request.result_mode is QueryResultMode.COUNT
    assert request.execution_mode is QueryExecutionMode.ON_DEMAND
    assert request.filters[0].operator is PredicateOperator.EQ
    assert request.model_dump(mode="json") == {
        "result_mode": "COUNT",
        "execution_mode": "ON_DEMAND",
        "subject_types": ["Battery"],
        "filters": [{"path": "chemistry", "operator": "EQ", "value": "NMC"}],
        "return_fields": None,
        "aggregate_path": None,
    }


def test_filter_validation_requires_fields_and_a_known_operator() -> None:
    with pytest.raises(ValidationError):
        PredicateFilter.model_validate({"operator": "EQ"})
    with pytest.raises(ValidationError):
        PredicateFilter.model_validate({"path": "chemistry", "operator": "NOT_AN_OPERATOR"})


@pytest.mark.parametrize(
    ("query_request", "message"),
    [
        (_request(result_mode=QueryResultMode.SUM), "aggregate_path is required"),
        (_request(result_mode=QueryResultMode.COUNT, aggregate_path="weight_kg"), "only supported for SUM"),
        (_request(subject_types=["   "]), "subject_types\\[0] must not be blank"),
    ],
)
def test_request_validation_matches_java_result_mode_rules(
    query_request: PredicateQueryRequest, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_request(query_request)


def test_project_payload_to_facts_flattens_payload_and_enforces_one_value_field() -> None:
    facts = project_payload_to_facts(
        {
            "name": "Battery A",
            "weight_kg": 12.5,
            "recyclable": True,
            "manufacturer": {"country": "CH"},
            "tags": ["Premium"],
            "components": [{"name": "Cell A", "mass": 3}],
            "ignored": None,
        },
        "issuerA-battery-a",
        "Battery",
    )
    by_path = {fact["path"]: fact for fact in facts}

    assert by_path["name"]["value_text"] == "Battery A"
    assert by_path["weight_kg"]["value_number"] == 12.5
    assert by_path["recyclable"]["value_boolean"] is True
    assert by_path["manufacturer.country"]["value_text"] == "CH"
    assert by_path["tags.contains_premium"]["value_boolean"] is True
    assert by_path["components.contains_cell_a"]["value_boolean"] is True
    assert by_path["components.cell_a_mass"]["value_number"] == 3
    assert "ignored" not in by_path

    for fact in facts:
        validate_fact_document(fact)
        assert sum(fact.get(field) is not None for field in ("value_text", "value_number", "value_boolean")) == 1

    with pytest.raises(ValueError, match="exactly one"):
        validate_fact_document(
            _fact("issuerA-battery-a", "invalid", value_text="text", value_number=1)
        )


@pytest.mark.parametrize(
    ("document", "filter_", "expected"),
    [
        ({"number": 2}, PredicateFilter(path="number", operator="EQ", value="2.0"), True),
        ({"enabled": True}, PredicateFilter(path="enabled", operator="EQ", value="true"), True),
        ({"kind": "NMC"}, PredicateFilter(path="kind", operator="IN", value=["LFP", "NMC"]), True),
        ({"weight": 10}, PredicateFilter(path="weight", operator="GT", value="9"), True),
        ({"weight": 10}, PredicateFilter(path="weight", operator="GTE", value="10"), True),
        ({"weight": 10}, PredicateFilter(path="weight", operator="LT", value="11"), True),
        ({"weight": 10}, PredicateFilter(path="weight", operator="LTE", value="10"), True),
        ({"kind": "NMC"}, PredicateFilter(path="kind", operator="NEQ", value="LFP"), True),
        ({"kind": "NMC"}, PredicateFilter(path="kind", operator="EXISTS"), True),
        ({"kind": "NMC"}, PredicateFilter(path="missing", operator="NOT_EXISTS"), True),
    ],
)
def test_operator_evaluation_semantics(document: dict[str, Any], filter_: PredicateFilter, expected: bool) -> None:
    assert matches_filter(document, filter_) is expected


def test_missing_paths_do_not_match_neq_and_not_exists_only_matches_missing() -> None:
    document = {"chemistry": "NMC"}

    assert not matches_filter(document, PredicateFilter(path="missing", operator="EQ", value="x"))
    assert not matches_filter(document, PredicateFilter(path="missing", operator="NEQ", value="x"))
    assert not matches_filter(document, PredicateFilter(path="missing", operator="EXISTS"))
    assert matches_filter(document, PredicateFilter(path="missing", operator="NOT_EXISTS"))
    assert not matches_filter(document, PredicateFilter(path="chemistry", operator="NOT_EXISTS"))


@pytest.mark.asyncio
async def test_indexed_matcher_groups_facts_and_can_use_a_mock_repository() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str] | None, list[str] | None]] = []

        async def find_by_request(
            self,
            request: PredicateQueryRequest,
            subject_types: list[str] | None,
            return_fields: list[str] | None = None,
        ) -> list[dict[str, Any]]:
            self.calls.append((subject_types, return_fields))
            return [
                _fact("a", "chemistry", value_text="NMC"),
                _fact("a", "weight_kg", value_number=320),
                _fact("a", "manufacturer.country", value_text="CH"),
            ]

    repository = FakeRepository()
    matcher = IndexedQueryMatcher(repository)
    request = _request(
        filters=[
            PredicateFilter(path="chemistry", operator="EQ", value="NMC"),
            PredicateFilter(path="manufacturer.country", operator="EQ", value="CH"),
        ],
        return_fields=["chemistry", "manufacturer.country"],
    )

    assert await matcher.select(request, ["Battery"]) == [{"chemistry": "NMC", "manufacturer.country": "CH"}]
    assert await matcher.count(request, ["Battery"]) == 1
    assert repository.calls == [(["Battery"], ["chemistry", "manufacturer.country"]), (["Battery"], None)]


def test_on_demand_matching_select_count_sum_and_java_return_fields() -> None:
    documents = [
        {"name": "Battery A", "chemistry": "NMC", "weight_kg": 320, "manufacturer": {"country": "CH"}},
        {"name": "Battery B", "chemistry": "LFP", "weight_kg": 410, "manufacturer": {"country": "DE"}},
        {"name": "Battery C", "chemistry": "NMC", "manufacturer": {"country": "US"}},
    ]
    matcher = OnDemandQueryMatcher(documents)
    select_request = _request(
        execution_mode=QueryExecutionMode.ON_DEMAND,
        filters=[PredicateFilter(path="chemistry", operator="EQ", value="NMC")],
        return_fields=["name", "manufacturer.country", "missing"],
    )
    count_request = select_request.model_copy(update={"result_mode": QueryResultMode.COUNT})
    sum_request = select_request.model_copy(
        update={"result_mode": QueryResultMode.SUM, "aggregate_path": "weight_kg"}
    )

    assert matcher.select(select_request) == [
        {"name": "Battery A", "manufacturer.country": "CH"},
        {"name": "Battery C", "manufacturer.country": "US"},
    ]
    assert matcher.count(count_request) == 2
    assert matcher.sum(sum_request) == 320.0
    # Java returns the complete payload when no return fields are requested.
    assert select_fields(documents[0], None) == documents[0]


def test_indexed_return_fields_and_result_construction() -> None:
    facts = {
        "chemistry": _fact("a", "chemistry", value_text="NMC"),
        "weight_kg": _fact("a", "weight_kg", value_number=320),
    }

    # The indexed Java matcher exposes flattened paths, while explicitly
    # requested paths retain the same dotted keys as on-demand SELECT.
    from generic_dpp_platform.queries.service import _select_indexed_fields

    assert _select_indexed_fields(facts, None) == {"chemistry": "NMC", "weight_kg": 320}
    assert _select_indexed_fields(facts, ["weight_kg", "missing"]) == {"weight_kg": 320}
    assert empty_response(_request(result_mode=QueryResultMode.SELECT), "issuerA").matches == []
    assert empty_response(_request(result_mode=QueryResultMode.COUNT), "issuerA").count == 0
    assert empty_response(
        _request(result_mode=QueryResultMode.SUM, aggregate_path="weight_kg"), "issuerA"
    ).aggregate == 0.0


def test_indexed_pipeline_contains_subject_and_predicate_constraints() -> None:
    from generic_dpp_platform.queries.service import _indexed_predicate_pipeline

    request = _request(
        filters=[
            PredicateFilter(path="manufacturing.facilityId", operator="IN", value=["factory-a", "factory-b"]),
            PredicateFilter(path="manufacturing.date", operator="GTE", value="2024-01-01"),
        ],
        return_fields=["serial_number"],
    )

    pipeline = _indexed_predicate_pipeline(request, ["PV_MODULE", "BATTERY"], request.return_fields)

    assert pipeline[0] == {"$match": {"subject_type": {"$in": ["PV_MODULE", "BATTERY"]}}}
    assert any("$group" in stage for stage in pipeline)
    assert {
        "facts": {
            "$elemMatch": {
                "path": "manufacturing.facilityId",
                "$or": [
                    {"value_text": "factory-a"},
                    {"value_text": "factory-b"},
                ],
            }
        }
    } in pipeline[2]["$match"]["$and"]
    assert {"$match": {"path": {"$in": ["serial_number"]}}} in pipeline


def test_subject_types_omitted_null_empty_and_legacy_single_type() -> None:
    assert PredicateQueryRequest.model_validate({"result_mode": "COUNT"}).subject_types is None
    assert PredicateQueryRequest.model_validate({"result_mode": "COUNT", "subject_types": None}).subject_types is None
    assert PredicateQueryRequest.model_validate({"result_mode": "COUNT", "subject_types": []}).subject_types == []
    assert PredicateQueryRequest.model_validate({"result_mode": "COUNT", "subject_type": "PV_MODULE"}).subject_types == ["PV_MODULE"]
    assert PredicateQueryRequest.model_validate(
        {"result_mode": "COUNT", "subject_type": "BATTERY", "subject_types": ["PV_MODULE"]}
    ).subject_types == ["PV_MODULE"]
