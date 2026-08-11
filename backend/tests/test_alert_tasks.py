from app.core.celery_app import celery_app


def test_celery_schedule_contains_due_scan() -> None:
    entry = celery_app.conf.beat_schedule["evaluate-due-alert-rules"]
    assert entry["task"] == "alerts.evaluate_due_rules"
    assert entry["schedule"] > 0


def test_alert_tasks_registered() -> None:
    celery_app.loader.import_default_modules()
    assert "alerts.evaluate_due_rules" in celery_app.tasks
    assert "alerts.evaluate_rule" in celery_app.tasks
