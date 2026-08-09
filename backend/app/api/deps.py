from typing import Annotated, Callable

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rbac import has_role
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.auth import UserModel, WorkspaceMembershipModel
from app.repositories.auth import AuthRepository
from app.schemas.auth import WorkspaceRole


bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_repository(db: Annotated[Session, Depends(get_db)]) -> AuthRepository:
    return AuthRepository(db)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserModel:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        user_id = decode_access_token(settings, credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc
    user = repo.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    return user


def get_current_active_user(user: Annotated[UserModel, Depends(get_current_user)]) -> UserModel:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    return user


def get_current_workspace(
    user: Annotated[UserModel, Depends(get_current_active_user)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    active_workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
) -> WorkspaceMembershipModel:
    memberships = repo.list_workspaces_for_user(user.id)
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No workspace membership")
    if active_workspace_id is None:
        return memberships[0]
    membership = repo.get_membership(user.id, active_workspace_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    return membership


def require_workspace_role(minimum: WorkspaceRole) -> Callable[[WorkspaceMembershipModel], WorkspaceMembershipModel]:
    def dependency(membership: Annotated[WorkspaceMembershipModel, Depends(get_current_workspace)]) -> WorkspaceMembershipModel:
        if not has_role(membership.role, minimum):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient workspace role")
        return membership

    return dependency
