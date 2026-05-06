from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from .utils.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("factory_starting")
    yield
    logger.info("factory_stopped")


app = FastAPI(
    title="DPP Platform Factory",
    version="0.1.0",
    lifespan=lifespan,
)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
