from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import hash_password, hash_token, new_refresh_token, slugify
from app.models.auth import AuthSessionModel, UserModel, WorkspaceMembershipModel, WorkspaceModel
from app.schemas.auth import RegisterRequest, WorkspaceRole


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user(self, user_id: str) -> UserModel | None:
        return self.db.get(UserModel, user_id)

    def get_user_by_email(self, email: str) -> UserModel | None:
        return self.db.scalars(select(UserModel).where(UserModel.email == email.lower())).first()

    def create_user_with_workspace(self, payload: RegisterRequest) -> UserModel:
        user = UserModel(email=payload.email.lower(), password_hash=hash_password(payload.password), display_name=payload.display_name)
        self.db.add(user)
        self.db.flush()
        prefix = (payload.display_name or payload.email.split("@")[0]).strip()
        workspace_name = payload.workspace_name or f"{prefix}'s Workspace"
        workspace = WorkspaceModel(name=workspace_name, slug=self.unique_slug(workspace_name))
        self.db.add(workspace)
        self.db.flush()
        self.db.add(WorkspaceMembershipModel(user_id=user.id, workspace_id=workspace.id, role="owner"))
        self.db.commit()
        self.db.refresh(user)
        return user

    def unique_slug(self, name: str) -> str:
        base = slugify(name, "workspace")[:100]
        slug = base
        counter = 2
        while self.db.scalars(select(WorkspaceModel).where(WorkspaceModel.slug == slug)).first() is not None:
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def list_workspaces_for_user(self, user_id: str) -> list[WorkspaceMembershipModel]:
        stmt = (
            select(WorkspaceMembershipModel)
            .options(joinedload(WorkspaceMembershipModel.workspace), joinedload(WorkspaceMembershipModel.user))
            .where(WorkspaceMembershipModel.user_id == user_id)
            .order_by(WorkspaceMembershipModel.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def get_membership(self, user_id: str, workspace_id: str, *, for_update: bool = False) -> WorkspaceMembershipModel | None:
        stmt = (
            select(WorkspaceMembershipModel)
            .options(joinedload(WorkspaceMembershipModel.workspace), joinedload(WorkspaceMembershipModel.user))
            .where(WorkspaceMembershipModel.user_id == user_id, WorkspaceMembershipModel.workspace_id == workspace_id)
        )
        if for_update:
            stmt = stmt.with_for_update(of=WorkspaceMembershipModel)
        return self.db.scalars(stmt).first()

    def get_workspace(self, workspace_id: str) -> WorkspaceModel | None:
        return self.db.get(WorkspaceModel, workspace_id)

    def create_workspace(self, user: UserModel, name: str) -> WorkspaceModel:
        workspace = WorkspaceModel(name=name, slug=self.unique_slug(name))
        self.db.add(workspace)
        self.db.flush()
        self.db.add(WorkspaceMembershipModel(user_id=user.id, workspace_id=workspace.id, role="owner"))
        self.db.commit()
        self.db.refresh(workspace)
        return workspace

    def update_workspace(self, workspace: WorkspaceModel, name: str | None) -> WorkspaceModel:
        if name is not None:
            workspace.name = name
            workspace.slug = self.unique_slug(name)
        self.db.commit()
        self.db.refresh(workspace)
        return workspace

    def list_members(self, workspace_id: str) -> list[WorkspaceMembershipModel]:
        stmt = (
            select(WorkspaceMembershipModel)
            .options(joinedload(WorkspaceMembershipModel.user))
            .where(WorkspaceMembershipModel.workspace_id == workspace_id)
            .order_by(WorkspaceMembershipModel.role.desc(), WorkspaceMembershipModel.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def owner_count(self, workspace_id: str) -> int:
        return self.db.scalar(select(func.count(WorkspaceMembershipModel.id)).where(WorkspaceMembershipModel.workspace_id == workspace_id, WorkspaceMembershipModel.role == "owner")) or 0

    def lock_workspace_memberships(self, workspace_id: str) -> None:
        stmt = select(WorkspaceMembershipModel.id).where(WorkspaceMembershipModel.workspace_id == workspace_id).with_for_update()
        self.db.execute(stmt).all()

    def add_member(self, workspace_id: str, user: UserModel, role: WorkspaceRole) -> WorkspaceMembershipModel:
        existing = self.get_membership(user.id, workspace_id)
        if existing is not None:
            existing.role = role
            self.db.commit()
            self.db.refresh(existing)
            return existing
        membership = WorkspaceMembershipModel(user_id=user.id, workspace_id=workspace_id, role=role)
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def update_member_role(self, membership: WorkspaceMembershipModel, role: WorkspaceRole) -> WorkspaceMembershipModel:
        membership.role = role
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def remove_member(self, membership: WorkspaceMembershipModel) -> None:
        self.db.delete(membership)
        self.db.commit()

    def create_session(self, user: UserModel, refresh_days: int, user_agent: str | None = None) -> tuple[AuthSessionModel, str]:
        token = new_refresh_token()
        session = AuthSessionModel(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=refresh_days),
            user_agent=user_agent[:256] if user_agent else None,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session, token

    def consume_refresh(self, token: str, refresh_days: int, user_agent: str | None = None) -> tuple[UserModel, str] | None:
        current = datetime.now(timezone.utc)
        session = self.db.scalars(
            select(AuthSessionModel)
            .options(joinedload(AuthSessionModel.user))
            .where(AuthSessionModel.token_hash == hash_token(token))
            .with_for_update(of=AuthSessionModel)
        ).first()
        if session is None:
            return None
        expires_at = session.expires_at if session.expires_at.tzinfo is not None else session.expires_at.replace(tzinfo=timezone.utc)
        if session.revoked_at is not None or expires_at <= current or not session.user.is_active:
            return None
        session.revoked_at = current
        replacement_token = new_refresh_token()
        replacement = AuthSessionModel(
            user_id=session.user.id,
            token_hash=hash_token(replacement_token),
            expires_at=current + timedelta(days=refresh_days),
            user_agent=user_agent[:256] if user_agent else None,
            last_used_at=current,
        )
        self.db.add(replacement)
        self.db.commit()
        return session.user, replacement_token

    def revoke_refresh(self, token: str) -> bool:
        session = self.db.scalars(select(AuthSessionModel).where(AuthSessionModel.token_hash == hash_token(token))).first()
        if session is None or session.revoked_at is not None:
            return False
        session.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        return True
