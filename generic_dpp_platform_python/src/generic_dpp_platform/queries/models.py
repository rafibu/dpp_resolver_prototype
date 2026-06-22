"""DTOs and enums for platform-local predicate queries.

Field names deliberately use the Java response contract's snake_case JSON
names.  The HTTP adapter additionally accepts Java's camelCase query parameter
names because Spring's ``@ModelAttribute`` binds those names in the Java
controller.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field
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
    result_mode: QueryResultMode
    execution_mode: QueryExecutionMode = QueryExecutionMode.INDEXED
    subject_type: str
    filters: list[PredicateFilter] = Field(default_factory=list)
    return_fields: list[str] | None = None
    aggregate_path: str | None = None


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

