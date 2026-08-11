from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_workspace
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.telemetry import TelemetryRepository
from app.schemas.metrics import (
    MetricAggregation,
    MetricBucket,
    MetricName,
    MetricQueryParams,
    MetricQueryResponse,
)
from app.services.metrics import MetricsService
from app.models.auth import WorkspaceMembershipModel

router = APIRouter(prefix="/metrics", tags=["metrics"])


def get_metrics_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MetricsService:
    return MetricsService(TelemetryRepository(db), settings.max_query_rows)


@router.get("/query", response_model=MetricQueryResponse, summary="Query telemetry metrics")
def query_metrics(
    service_dep: Annotated[MetricsService, Depends(get_metrics_service)],
    membership: Annotated[WorkspaceMembershipModel, Depends(get_current_workspace)],
    start: Annotated[datetime | None, Query(description="Inclusive UTC start timestamp")] = None,
    end: Annotated[datetime | None, Query(description="Inclusive UTC end timestamp")] = None,
    service: Annotated[str | None, Query(description="Optional service filter")] = None,
    region: Annotated[str | None, Query(description="Optional region filter")] = None,
    metric: MetricName = "latency",
    aggregation: MetricAggregation = "avg",
    bucket: MetricBucket = "1m",
) -> MetricQueryResponse:
    try:
        params = MetricQueryParams(
            start=start,
            end=end,
            service=service,
            region=region,
            metric=metric,
            aggregation=aggregation,
            bucket=bucket,
        )
        return service_dep.query(membership.workspace_id, params)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
