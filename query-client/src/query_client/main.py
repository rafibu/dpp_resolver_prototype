"""FastAPI application exposing the federated predicate query API.

Endpoints:

* ``POST /api/v1/federated-queries/predicate``      - start a job (returns immediately)
* ``GET  /api/v1/federated-queries/{job_id}``       - poll job status / progress
* ``GET  /api/v1/federated-queries/{job_id}/result``- fetch the (partial) result
* ``DELETE /api/v1/federated-queries/{job_id}``     - cancel a running job (optional)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_config
from .models import (
    FederatedPredicateQueryRequest,
    FederatedQueryResultResponse,
    FederatedQueryStartResponse,
    FederatedQueryStatusResponse,
)
from .service import FederatedQueryService
from .validation import QueryValidationError

API_PREFIX = "/api/v1/federated-queries"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    service = FederatedQueryService(config=config)
    app.state.service = service
    try:
        yield
    finally:
        await service.aclose()


def create_app() -> FastAPI:
    config = get_config()
    app = FastAPI(
        title="DPP Federated Predicate Query Client",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_allow_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _service() -> FederatedQueryService:
        return app.state.service

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        f"{API_PREFIX}/predicate",
        response_model=FederatedQueryStartResponse,
        status_code=202,
    )
    async def start_query(
        request: FederatedPredicateQueryRequest,
    ) -> FederatedQueryStartResponse:
        try:
            job = await _service().start(request)
        except QueryValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return job.to_start_response()

    @app.get(
        f"{API_PREFIX}/{{job_id}}",
        response_model=FederatedQueryStatusResponse,
    )
    async def get_status(job_id: str) -> FederatedQueryStatusResponse:
        job = await _service().store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
        return job.to_status_response()

    @app.get(
        f"{API_PREFIX}/{{job_id}}/result",
        response_model=FederatedQueryResultResponse,
    )
    async def get_result(job_id: str) -> FederatedQueryResultResponse:
        job = await _service().store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
        # While running, this returns the current partial result with status RUNNING.
        return job.to_result_response()

    @app.delete(f"{API_PREFIX}/{{job_id}}")
    async def cancel_query(job_id: str) -> dict[str, object]:
        job = await _service().store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
        cancelled = await _service().store.cancel_job(job_id)
        return {"job_id": job_id, "cancelled": cancelled}

    return app


app = create_app()
