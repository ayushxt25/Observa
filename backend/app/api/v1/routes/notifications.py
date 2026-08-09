from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_role
from app.core.config import Settings, get_settings
from app.core.rate_limit import RedisRateLimiter
from app.db.session import get_db
from app.models.auth import WorkspaceMembershipModel
from app.repositories.alerts import AlertRepository
from app.repositories.notifications import NotificationRepository, channel_out
from app.schemas.notifications import AlertChannelUpdate, NotificationChannelCreate, NotificationChannelListResponse, NotificationChannelOut, NotificationChannelPatch, NotificationDeliveryListResponse, NotificationDeliveryOut, NotificationDeliveryStatus, NotificationEventType, TestNotificationResponse
from app.services.notifications import UnsafeWebhookUrl, NotificationDeliveryService, validate_webhook_url

router = APIRouter(tags=["notifications"])


def get_notification_repository(db: Annotated[Session, Depends(get_db)]) -> NotificationRepository:
    return NotificationRepository(db)


def get_alert_repository(db: Annotated[Session, Depends(get_db)]) -> AlertRepository:
    return AlertRepository(db)


def delivery_out(delivery) -> NotificationDeliveryOut:
    return NotificationDeliveryOut.model_validate(delivery)


@router.get("/notification-channels", response_model=NotificationChannelListResponse, summary="List notification channels")
def list_channels(repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))]) -> NotificationChannelListResponse:
    return NotificationChannelListResponse(channels=[channel_out(channel) for channel in repo.list_channels(membership.workspace_id)])


@router.post("/notification-channels", response_model=NotificationChannelOut, status_code=status.HTTP_201_CREATED, summary="Create notification channel")
def create_channel(payload: NotificationChannelCreate, repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))], settings: Annotated[Settings, Depends(get_settings)]) -> NotificationChannelOut:
    if payload.type == "webhook" and payload.webhook_config is not None:
        try:
            validate_webhook_url(str(payload.webhook_config.target_url), settings)
        except UnsafeWebhookUrl as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return channel_out(repo.create_channel(membership.workspace_id, payload))


@router.get("/notification-channels/{channel_id}", response_model=NotificationChannelOut, summary="Get notification channel")
def get_channel(channel_id: str, repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))]) -> NotificationChannelOut:
    channel = repo.get_channel(membership.workspace_id, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    return channel_out(channel)


@router.patch("/notification-channels/{channel_id}", response_model=NotificationChannelOut, summary="Update notification channel")
def update_channel(channel_id: str, payload: NotificationChannelPatch, repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))], settings: Annotated[Settings, Depends(get_settings)]) -> NotificationChannelOut:
    channel = repo.get_channel(membership.workspace_id, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    if channel.type == "webhook" and payload.webhook_config is not None:
        try:
            validate_webhook_url(str(payload.webhook_config.target_url), settings)
        except UnsafeWebhookUrl as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return channel_out(repo.update_channel(channel, payload))


@router.delete("/notification-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete notification channel")
def delete_channel(channel_id: str, repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))]) -> None:
    channel = repo.get_channel(membership.workspace_id, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    repo.delete_channel(channel)


@router.post("/notification-channels/{channel_id}/test", response_model=TestNotificationResponse, summary="Send test notification")
def test_channel(channel_id: str, request: Request, repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))], settings: Annotated[Settings, Depends(get_settings)]) -> TestNotificationResponse:
    RedisRateLimiter(settings).check(request, "notification-test", settings.notification_test_rate_limit_per_minute)
    channel = repo.get_channel(membership.workspace_id, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    delivery = repo.create_test_delivery(membership.workspace_id, channel)
    NotificationDeliveryService(repo.db).enqueue_delivery(delivery.id)
    return TestNotificationResponse(delivery_id=delivery.id, status=delivery.status)


@router.put("/alerts/{rule_id}/notification-channels", response_model=AlertChannelUpdate, summary="Replace alert notification channels")
def set_alert_channels(rule_id: str, payload: AlertChannelUpdate, alerts: Annotated[AlertRepository, Depends(get_alert_repository)], repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))]) -> AlertChannelUpdate:
    if alerts.get_rule(rule_id, workspace_id=membership.workspace_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    try:
        return AlertChannelUpdate(channel_ids=repo.set_alert_channels(membership.workspace_id, rule_id, payload.channel_ids))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/notification-deliveries", response_model=NotificationDeliveryListResponse, summary="List notification deliveries")
def list_deliveries(
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
    status_filter: Annotated[NotificationDeliveryStatus | None, Query(alias="status")] = None,
    alert_rule_id: str | None = None,
    incident_id: str | None = None,
    channel_id: str | None = None,
    event_type: NotificationEventType | None = None,
    recent_hours: Annotated[int | None, Query(ge=1, le=24 * 30)] = None,
) -> NotificationDeliveryListResponse:
    rows = repo.list_deliveries(membership.workspace_id, status=status_filter, alert_rule_id=alert_rule_id, incident_id=incident_id, channel_id=channel_id, event_type=event_type, recent_hours=recent_hours)
    return NotificationDeliveryListResponse(deliveries=[delivery_out(row) for row in rows])


@router.get("/notification-deliveries/{delivery_id}", response_model=NotificationDeliveryOut, summary="Get notification delivery")
def get_delivery(delivery_id: str, repo: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))]) -> NotificationDeliveryOut:
    delivery = repo.get_delivery(membership.workspace_id, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification delivery not found")
    return delivery_out(delivery)
