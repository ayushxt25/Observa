from fastapi import APIRouter

from app.api.v1.routes import dashboards, metrics, services, telemetry

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(dashboards.router)
api_router.include_router(telemetry.router)
api_router.include_router(metrics.router)
api_router.include_router(services.router)
