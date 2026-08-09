from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token, new_api_key
from app.models.auth import WorkspaceApiKeyModel
from app.schemas.api_keys import ApiKeyCreate


class ApiKeyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_keys(self, workspace_id: str) -> list[WorkspaceApiKeyModel]:
        stmt = select(WorkspaceApiKeyModel).where(WorkspaceApiKeyModel.workspace_id == workspace_id).order_by(WorkspaceApiKeyModel.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def create_key(self, workspace_id: str, payload: ApiKeyCreate, created_by_user_id: str | None) -> tuple[WorkspaceApiKeyModel, str]:
        prefix, raw_key = new_api_key()
        key = WorkspaceApiKeyModel(
            workspace_id=workspace_id,
            name=payload.name,
            key_prefix=prefix,
            key_hash=hash_token(raw_key),
            expires_at=payload.expires_at,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(key)
        self.db.commit()
        self.db.refresh(key)
        return key, raw_key

    def get_key(self, workspace_id: str, key_id: str) -> WorkspaceApiKeyModel | None:
        stmt = select(WorkspaceApiKeyModel).where(WorkspaceApiKeyModel.workspace_id == workspace_id, WorkspaceApiKeyModel.id == key_id)
        return self.db.scalars(stmt).first()

    def revoke_key(self, key: WorkspaceApiKeyModel) -> None:
        key.revoked_at = datetime.now(timezone.utc)
        self.db.commit()

    def authenticate(self, raw_key: str) -> WorkspaceApiKeyModel | None:
        parts = raw_key.split("_", 3)
        if len(parts) != 4 or parts[0] != "obs" or parts[1] != "live" or not parts[2]:
            return None
        key = self.db.scalars(
            select(WorkspaceApiKeyModel)
            .where(WorkspaceApiKeyModel.key_prefix == parts[2], WorkspaceApiKeyModel.key_hash == hash_token(raw_key))
            .with_for_update(of=WorkspaceApiKeyModel)
        ).first()
        if key is None:
            return None
        now = datetime.now(timezone.utc)
        expires_at = key.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if key.revoked_at is not None or (expires_at is not None and expires_at <= now):
            return None
        last_used = key.last_used_at
        if last_used is None or (last_used.replace(tzinfo=timezone.utc) if last_used.tzinfo is None else last_used) < now - timedelta(seconds=60):
            key.last_used_at = now
            self.db.commit()
        return key
