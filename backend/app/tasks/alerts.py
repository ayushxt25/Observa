import logging

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.alerts import AlertEvaluationService

logger = logging.getLogger(__name__)


@celery_app.task(name="alerts.evaluate_rule", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def evaluate_rule(rule_id: str) -> dict[str, object]:
    with SessionLocal() as db:
        result = AlertEvaluationService(db).evaluate_rule(rule_id)
        return {"ruleId": result.alert.id, "triggered": result.triggered, "incidentId": result.incident_id}


@celery_app.task(name="alerts.evaluate_due_rules")
def evaluate_due_rules() -> dict[str, int]:
    with SessionLocal() as db:
        count = AlertEvaluationService(db).evaluate_due_rules()
        logger.info("alert_due_scan_completed count=%s", count)
        return {"evaluated": count}
