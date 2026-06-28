"""Pydantic v2 models and enums for the federated query client.

All wire JSON in this project is snake_case (see project conventions). Python
field names here are already snake_case, so the default pydantic serialization
produces the correct snake_case contract both for the federated API and for the
platform-local request body forwarded to each DPP platform.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class QueryResultMode(str, Enum):
    SELECT = "SELECT"
    COUNT = "COUNT"
    SUM = "SUM"


class QueryExecutionMode(str, Enum):
    ON_DEMAND = "ON_DEMAND"
    INDEXED = "INDEXED"


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


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class PlatformCallStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class PredicateFilter(BaseModel):
    """A single predicate filter forwarded verbatim to each platform.

    Operator-specific value rules (e.g. EXISTS must not carry a value, IN must
    carry a non-empty array) are enforced in :mod:`query_client.validation`,
    not here, because they are cross-field semantics.
    """

    path: str
    operator: PredicateOperator
    value: Optional[Any] = None


class FederatedPredicateQueryRequest(BaseModel):
    """Federation-level predicate query request accepted by the API.

    ``timeout_ms`` is the only field not forwarded to platforms; it bounds the
    whole federated fan-out. The platform-local body is produced by
    :meth:`to_platform_body`. ``subject_types`` is optional: omitted, ``null``,
    and ``[]`` all mean that each platform searches all local subject types.
    ``subject_type`` is accepted as a legacy input field only; new requests send
    ``subject_types``.
    """

    result_mode: QueryResultMode
    execution_mode: QueryExecutionMode = QueryExecutionMode.INDEXED
    subject_types: Optional[list[str]] = None
    filters: list[PredicateFilter] = Field(default_factory=list)
    return_fields: Optional[list[str]] = None
    aggregate_path: Optional[str] = None
    timeout_ms: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_subject_type(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "subject_types" in data:
            return data
        legacy = data.get("subject_type")
        if legacy is None:
            return data
        copied = dict(data)
        copied["subject_types"] = [legacy]
        return copied

    @property
    def subject_type(self) -> Optional[str]:
        """Compatibility accessor for older callers that expect one type."""
        if self.subject_types and len(self.subject_types) == 1:
            return self.subject_types[0]
        return None

    def to_platform_body(self) -> dict[str, Any]:
        """Build the snake_case platform-local query body.

        Only the platform-relevant fields are included; ``timeout_ms`` is
        intentionally omitted. Enum values are emitted as their string names.
        """
        body: dict[str, Any] = {
            "result_mode": self.result_mode.value,
            "execution_mode": self.execution_mode.value,
            "filters": [
                {
                    "path": f.path,
                    "operator": f.operator.value,
                    "value": f.value,
                }
                for f in self.filters
            ],
        }
        if self.subject_types:
            body["subject_types"] = list(self.subject_types)
        if self.return_fields is not None:
            body["return_fields"] = self.return_fields
        if self.aggregate_path is not None:
            body["aggregate_path"] = self.aggregate_path
        return body


# --------------------------------------------------------------------------- #
# Resolver / platform models
# --------------------------------------------------------------------------- #
class PlatformMapping(BaseModel):
    """A deduplicated platform discovered through the resolver registry."""

    platform_id: str
    base_url: str


class PlatformQueryResponse(BaseModel):
    """Platform-local predicate query response, preserved verbatim.

    Unknown extra fields are kept so the per-platform response can be returned
    to clients without loss.
    """

    model_config = ConfigDict(extra="allow")

    result_mode: QueryResultMode
    execution_mode: QueryExecutionMode
    platform_id: str
    count: Optional[int] = None
    aggregate: Optional[Decimal] = None
    matches: Optional[Any] = None

    @field_serializer("aggregate")
    def _serialize_aggregate(self, value: Optional[Decimal]) -> Optional[float]:
        return None if value is None else float(value)


class PlatformQueryResult(BaseModel):
    """Per-platform execution record within a federated job."""

    platform_id: str
    base_url: str
    status: PlatformCallStatus = PlatformCallStatus.PENDING
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    http_status: Optional[int] = None
    error_message: Optional[str] = None
    response: Optional[PlatformQueryResponse] = None


# --------------------------------------------------------------------------- #
# Merged / federated result models
# --------------------------------------------------------------------------- #
class CombinedQueryResult(BaseModel):
    """Merged federation-level result across all successful platforms."""

    result_mode: QueryResultMode
    execution_mode: QueryExecutionMode
    count: Optional[int] = None
    aggregate: Optional[Decimal] = None
    matches: Optional[list[Any]] = None
    source_platforms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_serializer("aggregate")
    def _serialize_aggregate(self, value: Optional[Decimal]) -> Optional[float]:
        return None if value is None else float(value)


class FederatedQueryJob(BaseModel):
    """Full in-memory state of a federated query job.

    This is the single source of truth held in the job store. The status and
    result API responses are projections of this object.
    """

    job_id: str
    status: JobStatus = JobStatus.PENDING
    query: FederatedPredicateQueryRequest
    timeout_ms: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total_platforms: int = 0
    completed_platforms: int = 0
    successful_platforms: int = 0
    failed_platforms: int = 0
    timed_out_platforms: int = 0
    complete: bool = False
    platform_results: list[PlatformQueryResult] = Field(default_factory=list)
    combined_result: Optional[CombinedQueryResult] = None
    error: Optional[str] = None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at is None:
            return None
        end = self.finished_at or datetime.now(self.started_at.tzinfo)
        return int((end - self.started_at).total_seconds() * 1000)

    def to_start_response(self) -> "FederatedQueryStartResponse":
        base = f"/api/v1/federated-queries/{self.job_id}"
        return FederatedQueryStartResponse(
            job_id=self.job_id,
            status=self.status,
            created_at=self.created_at,
            status_url=base,
            result_url=f"{base}/result",
        )

    def to_status_response(self) -> "FederatedQueryStatusResponse":
        return FederatedQueryStatusResponse(
            job_id=self.job_id,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            duration_ms=self.duration_ms,
            timeout_ms=self.timeout_ms,
            total_platforms=self.total_platforms,
            completed_platforms=self.completed_platforms,
            successful_platforms=self.successful_platforms,
            failed_platforms=self.failed_platforms,
            timed_out_platforms=self.timed_out_platforms,
            platform_results=self.platform_results,
        )

    def to_result_response(self) -> "FederatedQueryResultResponse":
        return FederatedQueryResultResponse(
            job_id=self.job_id,
            status=self.status,
            query=self.query,
            timeout_ms=self.timeout_ms,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            duration_ms=self.duration_ms,
            total_platforms=self.total_platforms,
            completed_platforms=self.completed_platforms,
            successful_platforms=self.successful_platforms,
            failed_platforms=self.failed_platforms,
            timed_out_platforms=self.timed_out_platforms,
            complete=self.complete,
            platform_results=self.platform_results,
            combined_result=self.combined_result,
            error=self.error,
        )


# --------------------------------------------------------------------------- #
# API response models
# --------------------------------------------------------------------------- #
class FederatedQueryStartResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    status_url: str
    result_url: str


class FederatedQueryStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    timeout_ms: int
    total_platforms: int
    completed_platforms: int
    successful_platforms: int
    failed_platforms: int
    timed_out_platforms: int
    platform_results: list[PlatformQueryResult]


class FederatedQueryResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    query: FederatedPredicateQueryRequest
    timeout_ms: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    total_platforms: int
    completed_platforms: int
    successful_platforms: int
    failed_platforms: int
    timed_out_platforms: int
    complete: bool
    platform_results: list[PlatformQueryResult]
    combined_result: Optional[CombinedQueryResult] = None
    error: Optional[str] = None
