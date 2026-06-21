"""Unit tests for the in-memory job store."""

import asyncio

import pytest

from query_client.job_store import JobStore
from query_client.models import FederatedPredicateQueryRequest, JobStatus


def _request():
    return FederatedPredicateQueryRequest.model_validate(
        {"result_mode": "COUNT", "subject_type": "battery"}
    )


@pytest.mark.asyncio
async def test_create_and_get_job():
    store = JobStore()
    job = await store.create_job("job-1", _request(), 1000)
    assert job.status is JobStatus.PENDING
    assert job.timeout_ms == 1000
    fetched = await store.get_job("job-1")
    assert fetched is job


@pytest.mark.asyncio
async def test_get_unknown_job_returns_none():
    store = JobStore()
    assert await store.get_job("nope") is None


@pytest.mark.asyncio
async def test_update_job_overwrites_entry():
    store = JobStore()
    job = await store.create_job("job-1", _request(), 1000)
    job.status = JobStatus.SUCCESS
    await store.update_job(job)
    assert (await store.get_job("job-1")).status is JobStatus.SUCCESS


@pytest.mark.asyncio
async def test_cancel_running_job_marks_failed():
    store = JobStore()
    job = await store.create_job("job-1", _request(), 1000)
    job.status = JobStatus.RUNNING

    async def _never():
        await asyncio.sleep(60)

    task = asyncio.create_task(_never())
    await store.register_task("job-1", task)

    cancelled = await store.cancel_job("job-1")
    assert cancelled is True
    assert job.status is JobStatus.FAILED
    assert job.error == "Job cancelled"
    assert job.finished_at is not None
    # Let the cancellation propagate.
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_without_task_returns_false():
    store = JobStore()
    await store.create_job("job-1", _request(), 1000)
    assert await store.cancel_job("job-1") is False


@pytest.mark.asyncio
async def test_cancel_completed_task_returns_false():
    store = JobStore()
    await store.create_job("job-1", _request(), 1000)

    async def _done():
        return None

    task = asyncio.create_task(_done())
    await task
    await store.register_task("job-1", task)
    assert await store.cancel_job("job-1") is False


@pytest.mark.asyncio
async def test_concurrent_creates_are_all_stored():
    store = JobStore()
    await asyncio.gather(
        *(store.create_job(f"job-{i}", _request(), 1000) for i in range(50))
    )
    for i in range(50):
        assert await store.get_job(f"job-{i}") is not None
