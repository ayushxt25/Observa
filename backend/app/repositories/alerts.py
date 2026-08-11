from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.alerts import AlertRuleModel, IncidentModel
from app.schemas.alerts import AlertRuleCreate, AlertRulePatch


class AlertRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_rules(self, workspace_id: str | None = None) -> list[AlertRuleModel]:
        stmt = select(AlertRuleModel).order_by(AlertRuleModel.created_at.desc(), AlertRuleModel.name)
        if workspace_id is not None:
            stmt = stmt.where(AlertRuleModel.workspace_id == workspace_id)
        return list(self.db.scalars(stmt).all())

    def get_rule(self, rule_id: str, *, workspace_id: str | None = None, for_update: bool = False) -> AlertRuleModel | None:
        stmt = select(AlertRuleModel).where(AlertRuleModel.id == rule_id)
        if workspace_id is not None:
            stmt = stmt.where(AlertRuleModel.workspace_id == workspace_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalars(stmt).first()

    def create_rule(self, payload: AlertRuleCreate, workspace_id: str, *, commit: bool = True) -> AlertRuleModel:
        rule = AlertRuleModel(**payload.model_dump(exclude={"notification_channel_ids"}), workspace_id=workspace_id)
        self.db.add(rule)
        if commit:
            self.db.commit()
            self.db.refresh(rule)
        else:
            self.db.flush()
        return rule

    def update_rule(self, rule: AlertRuleModel, payload: AlertRulePatch, *, commit: bool = True) -> AlertRuleModel:
        data = payload.model_dump(exclude_unset=True, exclude={"notification_channel_ids"})
        bucket = data.get("bucket", rule.bucket)
        window = data.get("evaluation_window_seconds", rule.evaluation_window_seconds)
        self._validate_bucket_window(bucket, window)
        for key, value in data.items():
            setattr(rule, key, value)
        if commit:
            self.db.commit()
            self.db.refresh(rule)
        else:
            self.db.flush()
        return rule

    def delete_rule(self, rule: AlertRuleModel, *, commit: bool = True) -> None:
        if self.incident_count(rule.id) > 0:
            raise ValueError("Alert rules with incident history cannot be deleted")
        self.db.delete(rule)
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def incident_count(self, rule_id: str) -> int:
        return self.db.scalar(select(func.count(IncidentModel.id)).where(IncidentModel.alert_rule_id == rule_id)) or 0

    def due_rules(self, now: datetime | None = None) -> list[AlertRuleModel]:
        current = now or datetime.now(timezone.utc)
        rules = list(self.db.scalars(select(AlertRuleModel).where(AlertRuleModel.enabled.is_(True))).all())
        due = []
        for rule in rules:
            evaluated = rule.last_evaluated_at
            if evaluated is None:
                due.append(rule)
                continue
            if evaluated.tzinfo is None:
                evaluated = evaluated.replace(tzinfo=timezone.utc)
            if evaluated <= current - timedelta(seconds=rule.evaluation_interval_seconds):
                due.append(rule)
        return due

    def active_incident(self, rule_id: str, *, for_update: bool = False) -> IncidentModel | None:
        stmt = select(IncidentModel).where(IncidentModel.alert_rule_id == rule_id, IncidentModel.status == "firing")
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalars(stmt).first()

    def create_incident(self, rule: AlertRuleModel, value: float, now: datetime) -> IncidentModel:
        incident = IncidentModel(
            alert_rule_id=rule.id,
            workspace_id=rule.workspace_id,
            status="firing",
            opened_at=now,
            triggering_value=value,
            threshold=rule.threshold,
            message=f"{rule.name} firing: {rule.metric} {rule.operator} {rule.threshold} (value {value:.3f})",
        )
        incident.alert_rule = rule
        self.db.add(incident)
        return incident

    def list_incidents(
        self,
        *,
        status: str | None = None,
        alert_rule_id: str | None = None,
        service: str | None = None,
        recent_hours: int | None = None,
        workspace_id: str | None = None,
    ) -> list[IncidentModel]:
        stmt = select(IncidentModel).options(joinedload(IncidentModel.alert_rule)).order_by(IncidentModel.status, IncidentModel.opened_at.desc())
        filters = []
        if status:
            filters.append(IncidentModel.status == status)
        if workspace_id:
            filters.append(IncidentModel.workspace_id == workspace_id)
        if alert_rule_id:
            filters.append(IncidentModel.alert_rule_id == alert_rule_id)
        if service:
            filters.append(AlertRuleModel.service == service)
            stmt = stmt.join(AlertRuleModel)
        if recent_hours:
            filters.append(IncidentModel.opened_at >= datetime.now(timezone.utc) - timedelta(hours=recent_hours))
        if filters:
            stmt = stmt.where(and_(*filters))
        return list(self.db.scalars(stmt).all())

    def get_incident(self, incident_id: str, workspace_id: str | None = None) -> IncidentModel | None:
        stmt = select(IncidentModel).options(joinedload(IncidentModel.alert_rule)).where(IncidentModel.id == incident_id)
        if workspace_id is not None:
            stmt = stmt.where(IncidentModel.workspace_id == workspace_id)
        return self.db.scalars(stmt).first()

    def _validate_bucket_window(self, bucket: str, window: int) -> None:
        if bucket == "1m" and window < 60:
            raise ValueError("evaluationWindowSeconds must cover at least one selected bucket")
        if bucket == "5m" and window < 300:
            raise ValueError("evaluationWindowSeconds must cover at least one selected bucket")
        if bucket == "1h" and window < 3600:
            raise ValueError("evaluationWindowSeconds must cover at least one selected bucket")
