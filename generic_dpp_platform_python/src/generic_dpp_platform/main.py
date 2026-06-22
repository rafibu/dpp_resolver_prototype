import structlog
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .admin.router import router as admin_router
from .dpps.exceptions import (
    DppAlreadyExistsException,
    DppCycleDetectedException,
    DppReferenceResolutionException,
    DppRevisionConflictException,
    NotFoundException,
    SchemaValidationException,
)
from .dpps.router import router as dpps_router
from .logging_config import configure_logging
from .queries.router import router as queries_router
from .schemas.router import router as schemas_router

configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("platform_starting")
    yield
    logger.info("platform_stopped")


app = FastAPI(
    title="Generic DPP Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):[0-9]+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _api_error(error: str, message: str, path: str, details: list[str] | None = None) -> dict:
    return {
        "error": error,
        "message": message,
        "details": details or [],
        "timestamp": datetime.now(UTC).isoformat(),
        "path": path,
    }


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=_api_error("Invalid Argument", str(exc), request.url.path),
    )


@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=_api_error("Not Found", str(exc), request.url.path),
    )


@app.exception_handler(SchemaValidationException)
async def schema_validation_handler(request: Request, exc: SchemaValidationException) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=_api_error(
            "Schema Validation Failed",
            str(exc),
            request.url.path,
            exc.validation_errors,
        ),
    )


@app.exception_handler(DppAlreadyExistsException)
async def dpp_already_exists_handler(request: Request, exc: DppAlreadyExistsException) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=_api_error("DPP Already Exists", str(exc), request.url.path),
    )


@app.exception_handler(DppRevisionConflictException)
async def revision_conflict_handler(request: Request, exc: DppRevisionConflictException) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=_api_error("Revision Conflict", str(exc), request.url.path),
    )


@app.exception_handler(DppCycleDetectedException)
async def cycle_detected_handler(request: Request, exc: DppCycleDetectedException) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=_api_error("Cycle Detected", str(exc), request.url.path),
    )


@app.exception_handler(DppReferenceResolutionException)
async def reference_resolution_handler(request: Request, exc: DppReferenceResolutionException) -> JSONResponse:
    return JSONResponse(
        status_code=424,
        content=_api_error("Reference Resolution Failed", str(exc), request.url.path),
    )


app.include_router(admin_router, prefix="/admin")
app.include_router(schemas_router, prefix="/schemas")
app.include_router(dpps_router, prefix="/dpps")
app.include_router(queries_router, prefix="/query")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
