import logging

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.notifications import NotificationDeliveryService

logger = logging.getLogger(__name__)


@celery_app.task(name="notifications.deliver", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def deliver_notification(delivery_id: str) -> dict[str, object]:
    with SessionLocal() as db:
        result = NotificationDeliveryService(db).deliver(delivery_id)
        logger.info("notification_delivery_completed delivery_id=%s delivered=%s retryable=%s", delivery_id, result.delivered, result.retryable)
        return {"deliveryId": delivery_id, "delivered": result.delivered, "retryable": result.retryable}


@celery_app.task(name="notifications.retry_due")
def retry_due_notifications() -> dict[str, int]:
    with SessionLocal() as db:
        count = NotificationDeliveryService(db).retry_due()
        logger.info("notification_retry_scan_completed count=%s", count)
        return {"queued": count}
