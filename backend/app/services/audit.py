from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.auth import UserModel, WorkspaceMembershipModel
from app.repositories.audit import AuditRepository

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "key_hash",
    "raw_key",
    "secret",
    "secret_encrypted",
    "authorization",
    "cookie",
    "smtp_password",
}


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = "".join(char for char in str(key).lower() if char.isalnum())
            if any("".join(char for char in sensitive.lower() if char.isalnum()) in normalized_key for sensitive in SENSITIVE_KEYS):
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = sanitize_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(before) | set(after))
    changed = [key for key in keys if before.get(key) != after.get(key)]
    return {
        "changedFields": changed,
        "before": sanitize_metadata({key: before.get(key) for key in changed}),
        "after": sanitize_metadata({key: after.get(key) for key in changed}),
    }


class AuditService:
    def __init__(self, db: Session) -> None:
        self.repo = AuditRepository(db)

    def record(
        self,
        *,
        workspace_id: str,
        action: str,
        resource_type: str,
        actor_type: str = "user",
        outcome: str = "success",
        actor_user_id: str | None = None,
        resource_id: str | None = None,
        request: Request | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        self.repo.create(
            workspace_id=workspace_id,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent")[:256] if request and request.headers.get("user-agent") else None,
            request_id=getattr(request.state, "request_id", None) if request else None,
            metadata=sanitize_metadata(metadata or {}),
            commit=commit,
        )

    def record_user(
        self,
        *,
        membership: WorkspaceMembershipModel,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        request: Request | None = None,
        metadata: dict[str, Any] | None = None,
        outcome: str = "success",
        commit: bool = True,
    ) -> None:
        self.record(
            workspace_id=membership.workspace_id,
            actor_user_id=membership.user_id,
            actor_type="user",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request=request,
            metadata=metadata,
            outcome=outcome,
            commit=commit,
        )

    def record_auth(
        self,
        *,
        action: str,
        outcome: str,
        user: UserModel | None,
        workspace_id: str | None,
        request: Request | None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        if workspace_id is None:
            return
        self.record(
            workspace_id=workspace_id,
            actor_user_id=user.id if user else None,
            actor_type="user",
            action=action,
            resource_type="auth_session",
            outcome=outcome,
            request=request,
            metadata=metadata,
            commit=commit,
        )
