"""DTOs and enums for platform-local predicate and traverse queries.

Field names deliberately use the Java response contract's snake_case JSON
names.  The HTTP adapter additionally accepts Java's camelCase query parameter
names because Spring's ``@ModelAttribute`` binds those names in the Java
controller.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Any


class QueryResultMode(str, Enum):
    SELECT = "SELECT"
    COUNT = "COUNT"
    SUM = "SUM"


class QueryExecutionMode(str, Enum):
    INDEXED = "INDEXED"
    ON_DEMAND = "ON_DEMAND"


class PredicateOperator(str, Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    IN = "IN"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"


class PredicateFilter(BaseModel):
    """One AND-connected predicate filter.

    This intentionally follows the Java DTO: path and operator are required,
    while the value remains untyped so equality and comparison preserve the
    source payload's runtime semantics.
    """

    path: str
    operator: PredicateOperator
    value: Any | None = None


class PredicateQueryRequest(BaseModel):
    """Platform-local predicate query over projected facts.

    ``subject_types`` is optional by design: an omitted field, explicit ``null``,
    or an empty list all mean that the platform should search all local DPP
    subject types. A non-empty list restricts the candidate current revisions to
    those subject types. The legacy ``subject_type`` field is accepted only as a
    compatibility fallback; ``subject_types`` takes precedence.
    """

    result_mode: QueryResultMode
    execution_mode: QueryExecutionMode = QueryExecutionMode.INDEXED
    subject_types: list[str] | None = None
    subject_type: str | None = Field(default=None, exclude=True)
    filters: list[PredicateFilter] = Field(default_factory=list)
    return_fields: list[str] | None = None
    aggregate_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_subject_type(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "subject_types" in data:
            return data
        legacy = data.get("subject_type")
        if legacy is None:
            return data
        copied = dict(data)
        copied["subject_types"] = [legacy]
        return copied


class PredicateQueryResponse(BaseModel):
    """Java-compatible predicate-query response shape.

    Inactive result fields are represented as ``null`` just as the Java DTO is
    serialized by Jackson's default configuration.
    """

    result_mode: QueryResultMode
    execution_mode: QueryExecutionMode
    platform_id: str
    count: int | None = None
    aggregate: float | None = None
    matches: Any | None = None


class TraverseSourceScope(BaseModel):
    """One Java-compatible ``sources[i]`` traverse-query scope."""

    subject_type: str
    reference_paths: list[str] | None = None


class TraverseQueryRequest(BaseModel):
    """Flattened Java ``TraverseQueryRequestDTO`` equivalent.

    ``sources`` deliberately remains required: the Java DTO declares it
    ``@NotNull`` even though an individual source's ``reference_paths`` is
    optional.
    """

    subject_type: str
    dpp_id: str
    execution_mode: QueryExecutionMode = QueryExecutionMode.INDEXED
    revision_number: int | None = None
    sources: list[TraverseSourceScope]


class TraverseQueryResponse(BaseModel):
    """Java-compatible ``TraverseQueryResponseDTO`` response body."""

    platform_id: str
    subject_type: str
    dpp_id: str
    matches: list[Any] = Field(default_factory=list)
