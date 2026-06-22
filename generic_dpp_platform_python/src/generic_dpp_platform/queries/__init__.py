"""Platform-local predicate-query support.

The package mirrors the Java platform's predicate-query model.  The immutable
DPP revisions remain authoritative; ``query_attribute_fact`` is a rebuildable
MongoDB materialization used only for INDEXED execution.
"""

from .models import (
    PredicateFilter,
    PredicateOperator,
    PredicateQueryRequest,
    PredicateQueryResponse,
    QueryExecutionMode,
    QueryResultMode,
)

__all__ = [
    "PredicateFilter",
    "PredicateOperator",
    "PredicateQueryRequest",
    "PredicateQueryResponse",
    "QueryExecutionMode",
    "QueryResultMode",
]
