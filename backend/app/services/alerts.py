from datetime import datetime, timedelta, timezone
import logging
import time

from sqlalchemy.orm import Session

from app.repositories.alerts import AlertRepository
from app.repositories.notifications import NotificationRepository
from app.query.engine import TelemetryQueryEngine
from app.query.schemas import QueryFilters, TelemetryQueryRequest
from app.schemas.alerts import AlertEvaluationResponse
from app.services.notifications import NotificationDeliveryService

logger = logging.getLogger(__name__)


ALERT_METRIC_TO_QUERY_METRIC = {
    "latency": "latency",
    "throughput": "throughput",
    "cpuUsage": "cpu_usage",
    "memoryUsage": "memory_usage",
    "errorRate": "error_rate",
    "payloadSize": "payload_size",
}


def compare_value(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    return value <= threshold


class AlertEvaluationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.alerts = AlertRepository(db)
        self.notifications = NotificationRepository(db)
        self.query_engine = TelemetryQueryEngine(db)

    def evaluate_rule(self, rule_id: str, now: datetime | None = None) -> AlertEvaluationResponse:
        started = time.perf_counter()
        rule = self.alerts.get_rule(rule_id, for_update=True)
        if rule is None:
            raise ValueError("Alert rule not found")
        current = now or datetime.now(timezone.utc)
        if not rule.enabled:
            return AlertEvaluationResponse(alert=rule, value=None, triggered=False)
        try:
            logger.info("alert_evaluation_started rule_id=%s metric=%s", rule.id, rule.metric)
            value = self._read_value(rule, current)
            triggered = value is not None and compare_value(value, rule.operator, rule.threshold)
            incident_id = None
            delivery_ids: list[str] = []
            active = self.alerts.active_incident(rule.id, for_update=True)
            rule.last_evaluated_at = current
            if triggered:
                rule.state = "firing"
                if active is None and not self._cooldown_active(rule, current):
                    incident = self.alerts.create_incident(rule, value, current)
                    rule.last_triggered_at = current
                    self.db.flush()
                    incident_id = incident.id
                    for channel in self.notifications.enabled_channels_for_alert(rule):
                        delivery = self.notifications.create_delivery(incident, channel, "firing")
                        if delivery is not None:
                            delivery_ids.append(delivery.id)
                    logger.info("alert_transition_firing rule_id=%s incident_id=%s value=%s", rule.id, incident.id, value)
                elif active is not None:
                    incident_id = active.id
            else:
                rule.state = "normal"
                if active is not None:
                    active.status = "resolved"
                    active.resolved_at = current
                    for channel in self.notifications.enabled_channels_for_alert(rule):
                        delivery = self.notifications.create_delivery(active, channel, "resolved")
                        if delivery is not None:
                            delivery_ids.append(delivery.id)
                    logger.info("alert_transition_resolved rule_id=%s incident_id=%s", rule.id, active.id)
            self.db.commit()
            delivery_service = NotificationDeliveryService(self.db)
            for delivery_id in delivery_ids:
                delivery_service.enqueue_delivery(delivery_id)
            self.db.refresh(rule)
            logger.info("alert_evaluation_completed rule_id=%s duration_ms=%.3f", rule.id, (time.perf_counter() - started) * 1000)
            return AlertEvaluationResponse(alert=rule, value=value, triggered=triggered, incident_id=incident_id)
        except Exception:
            self.db.rollback()
            logger.exception("alert_evaluation_failed rule_id=%s", rule_id)
            raise

    def evaluate_due_rules(self) -> int:
        count = 0
        for rule in self.alerts.due_rules():
            try:
                self.evaluate_rule(rule.id)
                count += 1
            except Exception:
                logger.exception("alert_due_rule_failed rule_id=%s", rule.id)
        return count

    def _read_value(self, rule, now: datetime) -> float | None:
        start = now - timedelta(seconds=rule.evaluation_window_seconds)
        response = self.query_engine.execute(
            rule.workspace_id,
            TelemetryQueryRequest(
                metric=ALERT_METRIC_TO_QUERY_METRIC[rule.metric],
                aggregation=rule.aggregation,
                start=start,
                end=now,
                bucket=rule.bucket,
                filters=QueryFilters(service=rule.service, region=rule.region),
            ),
        )
        if not response.series:
            return None
        points = response.series[0].points
        if not points:
            return None
        return points[-1].value

    def _cooldown_active(self, rule, now: datetime) -> bool:
        if rule.last_triggered_at is None:
            return False
        last_triggered = rule.last_triggered_at
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=timezone.utc)
        return now < last_triggered + timedelta(seconds=rule.cooldown_seconds)
