"""Federated predicate query client for the DPP prototype.

This package is an orchestration component. It validates a federated predicate
query, discovers registered platforms via the resolver, fans the query out to
each platform, records per-platform timing/failures, and merges the per-platform
responses into one federation-level result.

It deliberately does not evaluate DPP payloads and does not implement predicate
logic: every DPP platform remains responsible for evaluating a predicate query
over the revisions it hosts.
"""

from .config import Config, get_config
from .models import (
    CombinedQueryResult,
    FederatedPredicateQueryRequest,
    FederatedQueryJob,
    FederatedQueryResultResponse,
    FederatedQueryStartResponse,
    FederatedQueryStatusResponse,
    JobStatus,
    PlatformCallStatus,
    PlatformMapping,
    PlatformQueryResponse,
    PlatformQueryResult,
    PredicateFilter,
    PredicateOperator,
    QueryExecutionMode,
    QueryResultMode,
)
from .service import FederatedQueryService, run_federated_query

__all__ = [
    "Config",
    "get_config",
    "CombinedQueryResult",
    "FederatedPredicateQueryRequest",
    "FederatedQueryJob",
    "FederatedQueryResultResponse",
    "FederatedQueryStartResponse",
    "FederatedQueryStatusResponse",
    "JobStatus",
    "PlatformCallStatus",
    "PlatformMapping",
    "PlatformQueryResponse",
    "PlatformQueryResult",
    "PredicateFilter",
    "PredicateOperator",
    "QueryExecutionMode",
    "QueryResultMode",
    "FederatedQueryService",
    "run_federated_query",
]
