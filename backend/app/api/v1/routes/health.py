from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.db.session import check_database
from app.streaming.broker import TelemetryBroker

router = APIRouter(tags=["health"])


def get_health_broker(request: Request) -> TelemetryBroker:
    return request.app.state.broker


def get_database_ready() -> bool:
    try:
        return check_database()
    except Exception:
        return False


@router.get("/health", summary="Process liveness")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Dependency readiness")
async def ready(
    broker: Annotated[TelemetryBroker, Depends(get_health_broker)],
    database_ready: Annotated[bool, Depends(get_database_ready)],
) -> dict[str, object]:
    redis_ready = False
    try:
        redis_ready = await broker.ready()
    except Exception:
        redis_ready = False
    status = "ready" if database_ready and redis_ready else "degraded"
    return {"status": status, "database": database_ready, "redis": redis_ready}
