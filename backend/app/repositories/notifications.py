from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.alerts import AlertRuleModel, IncidentModel
from app.models.notifications import AlertNotificationChannelModel, NotificationChannelModel, NotificationDeliveryModel
from app.schemas.notifications import NotificationChannelCreate, NotificationChannelOut, NotificationChannelPatch


def _fernet(settings: Settings | None = None) -> Fernet:
    key_source = (settings or get_settings()).notification_secret_key.encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(sha256(key_source).digest()))


def encrypt_secret(secret: str, settings: Settings | None = None) -> str:
    return _fernet(settings).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(secret: str, settings: Settings | None = None) -> str:
    return _fernet(settings).decrypt(secret.encode("utf-8")).decode("utf-8")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def _load_config(channel: NotificationChannelModel) -> dict[str, Any]:
    return json.loads(channel.config_json)


def channel_out(channel: NotificationChannelModel) -> NotificationChannelOut:
    config = _load_config(channel)
    return NotificationChannelOut(
        id=channel.id,
        workspace_id=channel.workspace_id,
        name=channel.name,
        type=channel.type,
        enabled=channel.enabled,
        email_config=config if channel.type == "email" else None,
        webhook_url=config.get("targetUrl") if channel.type == "webhook" else None,
        webhook_label=config.get("label") if channel.type == "webhook" else None,
        has_secret=channel.secret_encrypted is not None,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_channels(self, workspace_id: str) -> list[NotificationChannelModel]:
        stmt = select(NotificationChannelModel).where(NotificationChannelModel.workspace_id == workspace_id).order_by(NotificationChannelModel.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get_channel(self, workspace_id: str, channel_id: str) -> NotificationChannelModel | None:
        return self.db.scalars(select(NotificationChannelModel).where(NotificationChannelModel.workspace_id == workspace_id, NotificationChannelModel.id == channel_id)).first()

    def create_channel(self, workspace_id: str, payload: NotificationChannelCreate) -> NotificationChannelModel:
        config: dict[str, Any]
        secret = None
        if payload.type == "email":
            assert payload.email_config is not None
            config = payload.email_config.model_dump(by_alias=True, mode="json")
        else:
            assert payload.webhook_config is not None
            config = payload.webhook_config.model_dump(by_alias=True, mode="json", exclude={"secret"})
            if payload.webhook_config.secret:
                secret = encrypt_secret(payload.webhook_config.secret)
        channel = NotificationChannelModel(workspace_id=workspace_id, name=payload.name, type=payload.type, enabled=payload.enabled, config_json=_json(config), secret_encrypted=secret)
        self.db.add(channel)
        self.db.commit()
        self.db.refresh(channel)
        return channel

    def update_channel(self, channel: NotificationChannelModel, payload: NotificationChannelPatch) -> NotificationChannelModel:
        data = payload.model_dump(exclude_unset=True)
        if "name" in data:
            channel.name = payload.name or channel.name
        if "enabled" in data and payload.enabled is not None:
            channel.enabled = payload.enabled
        if channel.type == "email" and payload.email_config is not None:
            channel.config_json = _json(payload.email_config.model_dump(by_alias=True, mode="json"))
        if channel.type == "webhook" and payload.webhook_config is not None:
            channel.config_json = _json(payload.webhook_config.model_dump(by_alias=True, mode="json", exclude={"secret"}))
            if payload.webhook_config.secret:
                channel.secret_encrypted = encrypt_secret(payload.webhook_config.secret)
        self.db.commit()
        self.db.refresh(channel)
        return channel

    def delete_channel(self, channel: NotificationChannelModel) -> None:
        self.db.delete(channel)
        self.db.commit()

    def set_alert_channels(self, workspace_id: str, alert_rule_id: str, channel_ids: list[str]) -> list[str]:
        valid_ids = set(self.db.scalars(select(NotificationChannelModel.id).where(NotificationChannelModel.workspace_id == workspace_id, NotificationChannelModel.id.in_(channel_ids))).all()) if channel_ids else set()
        if len(valid_ids) != len(set(channel_ids)):
            raise ValueError("One or more notification channels were not found")
        existing = list(self.db.scalars(select(AlertNotificationChannelModel).where(AlertNotificationChannelModel.workspace_id == workspace_id, AlertNotificationChannelModel.alert_rule_id == alert_rule_id)).all())
        for link in existing:
            if link.channel_id not in valid_ids:
                self.db.delete(link)
        existing_ids = {link.channel_id for link in existing}
        for channel_id in valid_ids - existing_ids:
            self.db.add(AlertNotificationChannelModel(workspace_id=workspace_id, alert_rule_id=alert_rule_id, channel_id=channel_id))
        self.db.commit()
        return sorted(valid_ids)

    def alert_channel_ids(self, workspace_id: str, alert_rule_id: str) -> list[str]:
        stmt = select(AlertNotificationChannelModel.channel_id).where(AlertNotificationChannelModel.workspace_id == workspace_id, AlertNotificationChannelModel.alert_rule_id == alert_rule_id)
        return list(self.db.scalars(stmt).all())

    def enabled_channels_for_alert(self, rule: AlertRuleModel) -> list[NotificationChannelModel]:
        stmt = (
            select(NotificationChannelModel)
            .join(AlertNotificationChannelModel, AlertNotificationChannelModel.channel_id == NotificationChannelModel.id)
            .where(AlertNotificationChannelModel.alert_rule_id == rule.id, AlertNotificationChannelModel.workspace_id == rule.workspace_id, NotificationChannelModel.enabled.is_(True))
        )
        return list(self.db.scalars(stmt).all())

    def create_delivery(self, incident: IncidentModel, channel: NotificationChannelModel, event_type: str) -> NotificationDeliveryModel | None:
        existing = self.db.scalars(
            select(NotificationDeliveryModel).where(
                NotificationDeliveryModel.incident_id == incident.id,
                NotificationDeliveryModel.channel_id == channel.id,
                NotificationDeliveryModel.event_type == event_type,
            )
        ).first()
        if existing is not None:
            return None
        delivery = NotificationDeliveryModel(
            workspace_id=incident.workspace_id,
            alert_rule_id=incident.alert_rule_id,
            incident_id=incident.id,
            channel_id=channel.id,
            channel_name=channel.name,
            channel_type=channel.type,
            channel_config_json=channel.config_json,
            channel_secret_encrypted=channel.secret_encrypted,
            event_type=event_type,
            status="pending",
            attempt_count=0,
        )
        self.db.add(delivery)
        self.db.flush()
        return delivery

    def create_test_delivery(self, workspace_id: str, channel: NotificationChannelModel) -> NotificationDeliveryModel:
        delivery = NotificationDeliveryModel(
            workspace_id=workspace_id,
            alert_rule_id="test",
            incident_id="test",
            channel_id=channel.id,
            channel_name=channel.name,
            channel_type=channel.type,
            channel_config_json=channel.config_json,
            channel_secret_encrypted=channel.secret_encrypted,
            event_type="test",
            status="pending",
            attempt_count=0,
        )
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def list_deliveries(
        self,
        workspace_id: str,
        *,
        status: str | None = None,
        alert_rule_id: str | None = None,
        incident_id: str | None = None,
        channel_id: str | None = None,
        event_type: str | None = None,
        recent_hours: int | None = None,
    ) -> list[NotificationDeliveryModel]:
        stmt = select(NotificationDeliveryModel).where(NotificationDeliveryModel.workspace_id == workspace_id).order_by(NotificationDeliveryModel.created_at.desc()).limit(200)
        filters = []
        if status:
            filters.append(NotificationDeliveryModel.status == status)
        if alert_rule_id:
            filters.append(NotificationDeliveryModel.alert_rule_id == alert_rule_id)
        if incident_id:
            filters.append(NotificationDeliveryModel.incident_id == incident_id)
        if channel_id:
            filters.append(NotificationDeliveryModel.channel_id == channel_id)
        if event_type:
            filters.append(NotificationDeliveryModel.event_type == event_type)
        if recent_hours:
            filters.append(NotificationDeliveryModel.created_at >= datetime.now(timezone.utc) - timedelta(hours=recent_hours))
        if filters:
            stmt = stmt.where(and_(*filters))
        return list(self.db.scalars(stmt).all())

    def get_delivery(self, workspace_id: str, delivery_id: str) -> NotificationDeliveryModel | None:
        return self.db.scalars(select(NotificationDeliveryModel).where(NotificationDeliveryModel.workspace_id == workspace_id, NotificationDeliveryModel.id == delivery_id)).first()

    def claim_delivery(self, delivery_id: str) -> NotificationDeliveryModel | None:
        delivery = self.db.scalars(select(NotificationDeliveryModel).where(NotificationDeliveryModel.id == delivery_id).with_for_update()).first()
        if delivery is None or delivery.status != "pending":
            return None
        delivery.status = "delivering"
        delivery.last_attempt_at = datetime.now(timezone.utc)
        delivery.attempt_count += 1
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def mark_delivered(self, delivery: NotificationDeliveryModel, response_code: int | None = None) -> None:
        delivery.status = "delivered"
        delivery.response_code = response_code
        delivery.error_summary = None
        delivery.next_retry_at = None
        delivery.delivered_at = datetime.now(timezone.utc)
        self.db.commit()

    def mark_failed(self, delivery: NotificationDeliveryModel, error: str, *, retryable: bool, response_code: int | None, max_attempts: int) -> None:
        delivery.response_code = response_code
        delivery.error_summary = error[:1000]
        if retryable and delivery.attempt_count < max_attempts:
            delay = min(300, 2 ** max(delivery.attempt_count - 1, 0) * 30)
            delivery.status = "pending"
            delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        else:
            delivery.status = "failed"
            delivery.next_retry_at = None
        self.db.commit()

    def due_deliveries(self, limit: int = 100, lease_seconds: int = 120) -> list[NotificationDeliveryModel]:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=lease_seconds)
        stale = list(self.db.scalars(
            select(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.status == "delivering")
            .where(NotificationDeliveryModel.last_attempt_at <= stale_before)
            .with_for_update()
            .limit(limit)
        ).all())
        for delivery in stale:
            delivery.status = "pending"
            delivery.next_retry_at = now
            delivery.error_summary = "Recovered stale in-progress delivery"
        if stale:
            self.db.commit()
        stmt = (
            select(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.status == "pending")
            .where((NotificationDeliveryModel.next_retry_at.is_(None)) | (NotificationDeliveryModel.next_retry_at <= now))
            .order_by(NotificationDeliveryModel.created_at)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
