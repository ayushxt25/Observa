from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
import json
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.audit import AuditEventModel
from app.schemas.audit import AuditEventFilters


def encode_cursor(created_at: datetime, event_id: str) -> str:
    raw = json.dumps({"createdAt": created_at.isoformat(), "id": event_id}, separators=(",", ":")).encode()
    return urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        payload = json.loads(urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(str(payload["createdAt"])), str(payload["id"])
    except Exception:
        raise ValueError("Invalid audit cursor") from None


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        workspace_id: str,
        actor_type: str,
        action: str,
        resource_type: str,
        outcome: str = "success",
        actor_user_id: str | None = None,
        resource_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> AuditEventModel:
        event = AuditEventModel(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata_json=json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
        )
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        else:
            self.db.flush()
        return event

    def list(self, workspace_id: str, filters: AuditEventFilters) -> tuple[list[AuditEventModel], str | None]:
        stmt = select(AuditEventModel).where(AuditEventModel.workspace_id == workspace_id)
        clauses = []
        if filters.actor_user_id:
            clauses.append(AuditEventModel.actor_user_id == filters.actor_user_id)
        if filters.actor_type:
            clauses.append(AuditEventModel.actor_type == filters.actor_type)
        if filters.action:
            clauses.append(AuditEventModel.action == filters.action)
        if filters.resource_type:
            clauses.append(AuditEventModel.resource_type == filters.resource_type)
        if filters.resource_id:
            clauses.append(AuditEventModel.resource_id == filters.resource_id)
        if filters.outcome:
            clauses.append(AuditEventModel.outcome == filters.outcome)
        if filters.start:
            clauses.append(AuditEventModel.created_at >= filters.start)
        if filters.end:
            clauses.append(AuditEventModel.created_at <= filters.end)
        if filters.cursor:
            decoded = decode_cursor(filters.cursor)
            if decoded is None:
                raise ValueError("Invalid audit cursor")
            created_at, event_id = decoded
            clauses.append(or_(AuditEventModel.created_at < created_at, and_(AuditEventModel.created_at == created_at, AuditEventModel.id < event_id)))
        if clauses:
            stmt = stmt.where(and_(*clauses))
        rows = list(self.db.scalars(stmt.order_by(AuditEventModel.created_at.desc(), AuditEventModel.id.desc()).limit(filters.limit + 1)).all())
        next_cursor = None
        if len(rows) > filters.limit:
            rows = rows[: filters.limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    def get(self, workspace_id: str, event_id: str) -> AuditEventModel | None:
        return self.db.scalars(select(AuditEventModel).where(AuditEventModel.workspace_id == workspace_id, AuditEventModel.id == event_id)).first()
