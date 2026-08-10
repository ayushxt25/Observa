from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_role
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.auth import WorkspaceMembershipModel
from app.query.engine import TelemetryQueryEngine
from app.query.schemas import TelemetryQueryRequest, TelemetryQueryResponse


router = APIRouter(prefix="/query", tags=["query"])


def get_query_engine(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TelemetryQueryEngine:
    return TelemetryQueryEngine(
        db,
        max_range_seconds=settings.query_max_range_seconds,
        max_points=settings.query_max_points,
        max_groups=settings.query_max_groups,
    )


@router.post("", response_model=TelemetryQueryResponse, summary="Run a workspace-scoped telemetry query")
def run_query(
    payload: TelemetryQueryRequest,
    engine: Annotated[TelemetryQueryEngine, Depends(get_query_engine)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
) -> TelemetryQueryResponse:
    try:
        return engine.execute(membership.workspace_id, payload)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

