from fastapi import APIRouter

from app.api.v1.routes import alerts, auth, dashboards, metrics, services, telemetry, workspaces

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(alerts.router)
api_router.include_router(dashboards.router)
api_router.include_router(telemetry.router)
api_router.include_router(metrics.router)
api_router.include_router(services.router)
