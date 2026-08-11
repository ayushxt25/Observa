from contextlib import asynccontextmanager
import logging
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1.router import api_router
from app.api.v1.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.streaming.broker import TelemetryBroker


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    broker = TelemetryBroker(settings)
    app.state.broker = broker
    await broker.connect()
    logger.info("observa_backend_started env=%s", settings.app_env)
    try:
        yield
    finally:
        await broker.close()
        logger.info("observa_backend_stopped")


app = FastAPI(
    title="Observa Telemetry API",
    version="0.1.0",
    summary="Persistent telemetry ingestion, query and streaming foundation for Observa.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

app.include_router(health_router)
app.include_router(api_router)
