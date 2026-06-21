"""In-memory federated query job store.

Jobs are kept in a dictionary keyed by ``job_id`` for the lifetime of the
process; this prototype intentionally avoids a database. Job objects are mutated
in place by the running fan-out task, so callers reading a job see live progress.
An :class:`asyncio.Lock` guards dictionary mutation. Because the asyncio event
loop is single-threaded, in-place field updates on a stored job do not require
additional locking.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from .models import FederatedPredicateQueryRequest, FederatedQueryJob, JobStatus


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, FederatedQueryJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def create_job(
        self, job_id: str, request: FederatedPredicateQueryRequest, timeout_ms: int
    ) -> FederatedQueryJob:
        job = FederatedQueryJob(
            job_id=job_id,
            status=JobStatus.PENDING,
            query=request,
            timeout_ms=timeout_ms,
            created_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._jobs[job_id] = job
        return job

    async def get_job(self, job_id: str) -> Optional[FederatedQueryJob]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update_job(self, job: FederatedQueryJob) -> None:
        async with self._lock:
            self._jobs[job.job_id] = job

    async def register_task(self, job_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            self._tasks[job_id] = task

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job's background task if present. Optional feature."""
        async with self._lock:
            task = self._tasks.get(job_id)
            job = self._jobs.get(job_id)
        if task is not None and not task.done():
            task.cancel()
            if job is not None and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                job.status = JobStatus.FAILED
                job.error = "Job cancelled"
                job.finished_at = datetime.now(timezone.utc)
            return True
        return False
