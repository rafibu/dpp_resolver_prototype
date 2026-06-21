"""Federated predicate query orchestration.

Coordinates resolver discovery, concurrent platform fan-out, timeout handling,
live job-status updates, and result merging. Usable two ways:

* :class:`FederatedQueryService` for the HTTP service (background jobs).
* :func:`run_federated_query` for the workload generator / CLI (run-to-completion).
"""

from __future__ import annotations

import asyncio
import httpx
import uuid
from datetime import datetime, timezone
from typing import Optional

from .config import Config, get_config
from .job_store import JobStore
from .merger import merge_results
from .models import (
    FederatedPredicateQueryRequest,
    FederatedQueryJob,
    FederatedQueryResultResponse,
    JobStatus,
    PlatformCallStatus,
    PlatformQueryResult,
)
from .platform_client import send_predicate_query
from .resolver_client import ResolverError, get_platforms
from .validation import validate_request


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Terminal per-platform statuses.
_TERMINAL = {
    PlatformCallStatus.SUCCESS,
    PlatformCallStatus.FAILED,
    PlatformCallStatus.TIMEOUT,
}


class FederatedQueryService:
    """Owns the job store and HTTP client used for federated query execution.

    A single ``httpx.AsyncClient`` is reused across platform calls. If one is not
    supplied, the service lazily creates one and is responsible for closing it
    via :meth:`aclose`.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        store: Optional[JobStore] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.config = config or get_config()
        self.store = store or JobStore()
        self._http_client = http_client
        self._owns_client = http_client is None

    # ----------------------------------------------------------------- #
    # HTTP-facing API
    # ----------------------------------------------------------------- #
    async def start(self, request: FederatedPredicateQueryRequest) -> FederatedQueryJob:
        """Validate, create a job, and schedule background execution.

        Returns immediately; the fan-out runs in an asyncio task. Raises
        :class:`~query_client.validation.QueryValidationError` if invalid.
        """
        validate_request(request)
        timeout_ms = request.timeout_ms or self.config.default_timeout_ms
        job_id = str(uuid.uuid4())
        job = await self.store.create_job(job_id, request, timeout_ms)
        task = asyncio.create_task(self._execute(job))
        await self.store.register_task(job_id, task)
        return job

    async def run_to_completion(
        self, request: FederatedPredicateQueryRequest
    ) -> FederatedQueryResultResponse:
        """Validate and execute a federated query, awaiting the final result.

        Used by the workload generator and the CLI. Does not schedule a detached
        background task; the job is run inline.
        """
        validate_request(request)
        timeout_ms = request.timeout_ms or self.config.default_timeout_ms
        job_id = str(uuid.uuid4())
        job = await self.store.create_job(job_id, request, timeout_ms)
        await self._execute(job)
        return job.to_result_response()

    async def aclose(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "FederatedQueryService":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    # ----------------------------------------------------------------- #
    # Execution
    # ----------------------------------------------------------------- #
    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._build_timeout())
        return self._http_client

    def _build_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.config.http_connect_timeout_ms / 1000,
            read=self.config.http_read_timeout_ms / 1000,
            write=self.config.http_read_timeout_ms / 1000,
            pool=self.config.http_connect_timeout_ms / 1000,
        )

    async def _execute(self, job: FederatedQueryJob) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = _now()
        client = self._client()

        # 1. Discover platforms.
        try:
            platforms = await get_platforms(client, self.config)
        except ResolverError as exc:
            self._fail_discovery(job, str(exc))
            return
        except asyncio.CancelledError:
            self._mark_cancelled(job)
            raise

        job.total_platforms = len(platforms)

        # 2. Prepare a per-platform result record (PENDING) for live polling.
        results = [
            PlatformQueryResult(platform_id=p.platform_id, base_url=p.base_url)
            for p in platforms
        ]
        job.platform_results = results

        if not platforms:
            # Nothing to query: an empty federation is a complete, successful result.
            job.combined_result = merge_results(job.query, results)
            self._finalize(job)
            return

        body = job.query.to_platform_body()
        timeout_s = job.timeout_ms / 1000

        # 3 & 4. Fan out concurrently.
        tasks = [
            asyncio.create_task(
                send_predicate_query(client, platform, body, self.config, result)
            )
            for platform, result in zip(platforms, results)
        ]

        # 5-8. Wait for completion or the federation timeout.
        try:
            _, pending = await asyncio.wait(tasks, timeout=timeout_s)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._mark_cancelled(job)
            raise

        if pending:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        self._mark_timeouts(results)

        # 9 & 10. Merge and store the final result.
        job.combined_result = merge_results(job.query, results)
        self._finalize(job)

    # ----------------------------------------------------------------- #
    # Status bookkeeping
    # ----------------------------------------------------------------- #
    def _mark_timeouts(self, results: list[PlatformQueryResult]) -> None:
        """Mark any platform call that never reached a terminal status as TIMEOUT."""
        for result in results:
            if result.status not in _TERMINAL:
                result.status = PlatformCallStatus.TIMEOUT
                result.error_message = "Platform did not respond before the federation timeout"
                result.finished_at = _now()
                if result.started_at is not None:
                    result.duration_ms = int(
                        (result.finished_at - result.started_at).total_seconds() * 1000
                    )

    def _finalize(self, job: FederatedQueryJob) -> None:
        """Recompute aggregate counts (after merge) and the overall job status."""
        results = job.platform_results
        successful = sum(1 for r in results if r.status is PlatformCallStatus.SUCCESS)
        failed = sum(1 for r in results if r.status is PlatformCallStatus.FAILED)
        timed_out = sum(1 for r in results if r.status is PlatformCallStatus.TIMEOUT)

        job.successful_platforms = successful
        job.failed_platforms = failed
        job.timed_out_platforms = timed_out
        job.completed_platforms = successful + failed + timed_out
        job.complete = job.total_platforms > 0 and successful == job.total_platforms
        if job.total_platforms == 0:
            job.complete = True
        job.status = self._derive_status(job.total_platforms, successful, failed, timed_out)
        job.finished_at = _now()

    @staticmethod
    def _derive_status(total: int, successful: int, failed: int, timed_out: int) -> JobStatus:
        if total == 0:
            return JobStatus.SUCCESS
        if successful == total:
            return JobStatus.SUCCESS
        if successful == 0:
            # No platform succeeded: classify by the dominant failure reason.
            if timed_out >= failed and timed_out > 0:
                return JobStatus.TIMEOUT
            return JobStatus.FAILED
        return JobStatus.PARTIAL

    def _fail_discovery(self, job: FederatedQueryJob, message: str) -> None:
        job.error = message
        job.combined_result = merge_results(job.query, [])
        job.combined_result.warnings.append(message)
        job.status = JobStatus.FAILED
        job.complete = False
        job.finished_at = _now()

    def _mark_cancelled(self, job: FederatedQueryJob) -> None:
        if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            job.status = JobStatus.FAILED
            job.error = "Job cancelled"
            job.finished_at = _now()


async def run_federated_query(
    request: FederatedPredicateQueryRequest,
    config: Optional[Config] = None,
) -> FederatedQueryResultResponse:
    """Importable convenience entry point: run a federated query to completion.

    Creates a short-lived service (and HTTP client), executes the query inline,
    and returns the full federated result. Intended for the workload generator
    and the ``run_query`` CLI.
    """
    async with FederatedQueryService(config=config) as service:
        return await service.run_to_completion(request)
