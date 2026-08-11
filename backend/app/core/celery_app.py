from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "observa",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.alerts", "app.tasks.notifications"],
)
celery_app.conf.update(
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    beat_schedule={
        "evaluate-due-alert-rules": {
            "task": "alerts.evaluate_due_rules",
            "schedule": float(settings.alert_scan_interval_seconds),
        },
        "retry-due-notifications": {
            "task": "notifications.retry_due",
            "schedule": float(settings.notification_retry_scan_interval_seconds),
        },
    },
)
