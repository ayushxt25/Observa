from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import smtplib
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.alerts import AlertRuleModel, IncidentModel
from app.models.notifications import NotificationDeliveryModel
from app.repositories.notifications import NotificationRepository, decrypt_secret

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    retryable: bool
    response_code: int | None = None
    error: str | None = None


class UnsafeWebhookUrl(ValueError):
    pass


def validate_webhook_url(url: str, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeWebhookUrl("Webhook URL must use http or https")
    if parsed.scheme != "https" and not cfg.webhook_allow_private_networks:
        raise UnsafeWebhookUrl("Webhook URL must use https unless local webhook testing is enabled")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeWebhookUrl("Webhook host could not be resolved") from exc
    if cfg.webhook_allow_private_networks:
        return
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeWebhookUrl("Webhook URL resolves to a restricted network")


def delivery_payload(delivery: NotificationDeliveryModel, rule: AlertRuleModel | None, incident: IncidentModel | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "schemaVersion": "2026-08-09",
        "deliveryId": delivery.id,
        "eventType": delivery.event_type,
        "workspaceId": delivery.workspace_id,
        "alertRuleId": delivery.alert_rule_id,
        "alertName": rule.name if rule else "Test notification",
        "incidentId": delivery.incident_id,
        "incidentStatus": incident.status if incident else delivery.event_type,
        "metric": rule.metric if rule else None,
        "triggeringValue": incident.triggering_value if incident else None,
        "threshold": incident.threshold if incident else None,
        "operator": rule.operator if rule else None,
        "service": rule.service if rule else None,
        "region": rule.region if rule else None,
        "openedAt": incident.opened_at.isoformat() if incident else None,
        "resolvedAt": incident.resolved_at.isoformat() if incident and incident.resolved_at else None,
        "timestamp": now.isoformat(),
    }


class NotificationDeliveryService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.notifications = NotificationRepository(db)

    def create_deliveries_for_incident(self, incident: IncidentModel, event_type: str) -> list[str]:
        rule = self.db.get(AlertRuleModel, incident.alert_rule_id)
        if rule is None:
            return []
        created: list[str] = []
        for channel in self.notifications.enabled_channels_for_alert(rule):
            delivery = self.notifications.create_delivery(incident, channel, event_type)
            if delivery is not None:
                created.append(delivery.id)
        self.db.commit()
        for delivery_id in created:
            self.enqueue_delivery(delivery_id)
        return created

    def enqueue_delivery(self, delivery_id: str) -> None:
        try:
            from app.tasks.notifications import deliver_notification

            deliver_notification.delay(delivery_id)
        except Exception:
            logger.exception("notification_enqueue_failed delivery_id=%s", delivery_id)

    def deliver(self, delivery_id: str) -> DeliveryResult:
        delivery = self.notifications.claim_delivery(delivery_id)
        if delivery is None:
            return DeliveryResult(delivered=False, retryable=False, error="Delivery not claimable")
        rule = self.db.get(AlertRuleModel, delivery.alert_rule_id) if delivery.alert_rule_id else None
        incident = self.db.get(IncidentModel, delivery.incident_id) if delivery.incident_id else None
        try:
            result = self._send(delivery, rule, incident)
            if result.delivered:
                self.notifications.mark_delivered(delivery, result.response_code)
            else:
                self.notifications.mark_failed(delivery, result.error or "Delivery failed", retryable=result.retryable, response_code=result.response_code, max_attempts=self.settings.notification_max_attempts)
            return result
        except Exception as exc:
            logger.exception("notification_delivery_failed delivery_id=%s channel_id=%s", delivery.id, delivery.channel_id)
            self.notifications.mark_failed(delivery, str(exc), retryable=True, response_code=None, max_attempts=self.settings.notification_max_attempts)
            return DeliveryResult(delivered=False, retryable=True, error=str(exc))

    def retry_due(self) -> int:
        deliveries = self.notifications.due_deliveries(lease_seconds=self.settings.notification_delivery_lease_seconds)
        for delivery in deliveries:
            self.enqueue_delivery(delivery.id)
        return len(deliveries)

    def _send(self, delivery: NotificationDeliveryModel, rule: AlertRuleModel | None, incident: IncidentModel | None) -> DeliveryResult:
        if delivery.channel_type == "webhook":
            return self._send_webhook(delivery, rule, incident)
        return self._send_email(delivery, rule, incident)

    def _send_webhook(self, delivery: NotificationDeliveryModel, rule: AlertRuleModel | None, incident: IncidentModel | None) -> DeliveryResult:
        config = json.loads(delivery.channel_config_json)
        url = str(config["targetUrl"])
        validate_webhook_url(url, self.settings)
        body = json.dumps(delivery_payload(delivery, rule, incident), separators=(",", ":"), sort_keys=True).encode("utf-8")
        headers = {"content-type": "application/json", "x-observa-event": delivery.event_type, "x-observa-delivery-id": delivery.id}
        if delivery.channel_secret_encrypted:
            secret = decrypt_secret(delivery.channel_secret_encrypted, self.settings)
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))
            signature = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + body, sha256).hexdigest()
            headers["x-observa-timestamp"] = timestamp
            headers["x-observa-signature"] = f"sha256={signature}"
        with httpx.Client(timeout=self.settings.webhook_timeout_seconds, follow_redirects=False) as client:
            response = client.post(url, content=body, headers=headers)
        if 200 <= response.status_code < 300:
            return DeliveryResult(delivered=True, retryable=False, response_code=response.status_code)
        retryable = response.status_code in {408, 429} or response.status_code >= 500
        return DeliveryResult(delivered=False, retryable=retryable, response_code=response.status_code, error=f"Webhook returned HTTP {response.status_code}")

    def _send_email(self, delivery: NotificationDeliveryModel, rule: AlertRuleModel | None, incident: IncidentModel | None) -> DeliveryResult:
        if not self.settings.smtp_host:
            return DeliveryResult(delivered=False, retryable=True, error="SMTP is not configured")
        config = json.loads(delivery.channel_config_json)
        recipients = config["recipients"]
        subject = self._single_line(f"Observa alert {delivery.event_type}: {rule.name if rule else 'test notification'}")
        text = self._email_text(delivery, rule, incident)
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.smtp_from
        message["To"] = ", ".join(recipients)
        message.set_content(text)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as smtp:
                if self.settings.smtp_tls:
                    smtp.starttls()
                if self.settings.smtp_username and self.settings.smtp_password:
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(message)
            return DeliveryResult(delivered=True, retryable=False)
        except smtplib.SMTPRecipientsRefused as exc:
            return DeliveryResult(delivered=False, retryable=False, error=f"SMTP recipients refused: {len(exc.recipients)}")
        except smtplib.SMTPException as exc:
            return DeliveryResult(delivered=False, retryable=True, error=str(exc))

    def _email_text(self, delivery: NotificationDeliveryModel, rule: AlertRuleModel | None, incident: IncidentModel | None) -> str:
        if rule is None or incident is None:
            return "This is a test notification from Observa."
        lines = [
            f"Alert: {rule.name}",
            f"Event: {delivery.event_type}",
            f"Metric: {rule.metric} {rule.operator} {rule.threshold}",
            f"Value: {incident.triggering_value:.3f}",
            f"Service: {rule.service or 'any'}",
            f"Region: {rule.region or 'any'}",
            f"Incident: {incident.id}",
            f"Opened: {incident.opened_at.isoformat()}",
        ]
        if incident.resolved_at:
            lines.append(f"Resolved: {incident.resolved_at.isoformat()}")
        return "\n".join(lines)

    def _single_line(self, value: str) -> str:
        return " ".join(value.splitlines())
