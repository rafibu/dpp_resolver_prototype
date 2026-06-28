"""FastAPI integration tests exercising the HTTP endpoints end-to-end.

The app is driven through ``httpx.ASGITransport`` in the test's own event loop so
that the background fan-out task scheduled by ``start`` actually progresses
between polls. The service's HTTP client is replaced with a routing mock
transport, so no real network is used.
"""

import asyncio
import httpx
import pytest

from query_client.main import create_app
from support import (
    json_handler,
    make_service,
    make_transport,
    resolver_handler,
    select_payload,
)


def _app_with(handlers):
    transport = make_transport(handlers)
    service = make_service(transport)
    app = create_app()
    app.state.service = service  # bypass lifespan; inject mock-backed service
    return app, service


async def _poll_until_terminal(client, status_url, attempts=200):
    for _ in range(attempts):
        resp = await client.get(status_url)
        data = resp.json()
        if data["status"] not in ("PENDING", "RUNNING"):
            return data
        await asyncio.sleep(0.01)
    raise AssertionError("job did not reach a terminal state")


@pytest.mark.asyncio
async def test_health():
    app, _ = _app_with({})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_start_poll_result_select_flow():
    handlers = {
        "resolver": resolver_handler(),
        "platform-a": json_handler(select_payload("platform-a", [{"dpp_id": "a-1", "version": 1}]), delay=0.02),
        "platform-b": json_handler(select_payload("platform-b", [{"dpp_id": "b-1", "version": 1}]), delay=0.02),
    }
    app, service = _app_with(handlers)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post(
            "/api/v1/federated-queries/predicate",
            json={"result_mode": "SELECT", "subject_types": ["battery"]},
        )
        assert start.status_code == 202
        body = start.json()
        job_id = body["job_id"]
        assert body["status"] in ("PENDING", "RUNNING")
        assert body["status_url"].endswith(job_id)
        assert body["result_url"].endswith(f"{job_id}/result")

        final = await _poll_until_terminal(client, body["status_url"])
        assert final["status"] == "SUCCESS"
        assert final["total_platforms"] == 2
        assert final["completed_platforms"] == 2

        result = await client.get(body["result_url"])
        rdata = result.json()
        assert rdata["status"] == "SUCCESS"
        assert rdata["complete"] is True
        assert rdata["combined_result"]["count"] == 2
        assert {m["platform_id"] for m in rdata["combined_result"]["matches"]} == {"platform-a", "platform-b"}

    await service.aclose()


@pytest.mark.asyncio
async def test_invalid_request_returns_422():
    app, service = _app_with({"resolver": resolver_handler()})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # aggregate_path is required for SUM -> semantic validation error.
        resp = await client.post(
            "/api/v1/federated-queries/predicate",
            json={"result_mode": "SUM", "subject_types": ["battery"]},
        )
    assert resp.status_code == 422
    await service.aclose()


@pytest.mark.asyncio
async def test_pydantic_validation_error_returns_422():
    app, service = _app_with({"resolver": resolver_handler()})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/federated-queries/predicate",
            json={"result_mode": "NONSENSE", "subject_types": ["battery"]},
        )
    assert resp.status_code == 422
    await service.aclose()


@pytest.mark.asyncio
async def test_unknown_job_returns_404():
    app, service = _app_with({})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/federated-queries/missing")).status_code == 404
        assert (await client.get("/api/v1/federated-queries/missing/result")).status_code == 404
        assert (await client.delete("/api/v1/federated-queries/missing")).status_code == 404
    await service.aclose()


@pytest.mark.asyncio
async def test_partial_result_while_running_then_completes():
    # Slow platforms so we can observe a RUNNING partial result first.
    handlers = {
        "resolver": resolver_handler(),
        "platform-a": json_handler(select_payload("platform-a", []), delay=0.15),
        "platform-b": json_handler(select_payload("platform-b", []), delay=0.15),
    }
    app, service = _app_with(handlers)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = (await client.post(
            "/api/v1/federated-queries/predicate",
            json={"result_mode": "SELECT", "subject_types": ["battery"], "timeout_ms": 5000},
        )).json()

        # Immediately fetch the result: it should be a partial RUNNING snapshot.
        running = (await client.get(start["result_url"])).json()
        assert running["status"] in ("PENDING", "RUNNING")
        assert running["complete"] is False

        final = await _poll_until_terminal(client, start["status_url"])
        assert final["status"] == "SUCCESS"
    await service.aclose()


@pytest.mark.asyncio
async def test_delete_cancels_running_job():
    handlers = {
        "resolver": resolver_handler(),
        "platform-a": json_handler(select_payload("platform-a", []), delay=5.0),
        "platform-b": json_handler(select_payload("platform-b", []), delay=5.0),
    }
    app, service = _app_with(handlers)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = (await client.post(
            "/api/v1/federated-queries/predicate",
            json={"result_mode": "SELECT", "subject_types": ["battery"], "timeout_ms": 10000},
        )).json()
        await asyncio.sleep(0.02)  # let it reach RUNNING
        deleted = await client.delete(start["status_url"])
        assert deleted.status_code == 200
        assert deleted.json()["cancelled"] is True

        status = (await client.get(start["status_url"])).json()
        assert status["status"] == "FAILED"
    await service.aclose()
