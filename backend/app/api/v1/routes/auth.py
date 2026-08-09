from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_auth_repository, get_current_active_user
from app.core import audit_actions
from app.core.config import Settings, get_settings
from app.core.rate_limit import RedisRateLimiter
from app.core.security import create_access_token, verify_password
from app.models.auth import UserModel, WorkspaceMembershipModel, WorkspaceModel
from app.repositories.auth import AuthRepository
from app.schemas.auth import AuthResult, LoginRequest, RegisterRequest, UserOut, WorkspaceOut
from app.services.audit import AuditService

router = APIRouter(prefix="/auth", tags=["auth"])


def check_auth_rate_limit(request: Request, settings: Settings, action: str, limit: int) -> None:
    RedisRateLimiter(settings).check(request, action, limit)


def workspace_out(membership: WorkspaceMembershipModel) -> WorkspaceOut:
    workspace = membership.workspace
    return WorkspaceOut(id=workspace.id, name=workspace.name, slug=workspace.slug, role=membership.role, created_at=workspace.created_at, updated_at=workspace.updated_at)


def auth_result(user: UserModel, repo: AuthRepository, settings: Settings, response: Response, request: Request) -> AuthResult:
    _, refresh_token = repo.create_session(user, settings.refresh_token_days, request.headers.get("user-agent"))
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )
    return AuthResult(access_token=create_access_token(settings, user.id), user=user, workspaces=[workspace_out(item) for item in repo.list_workspaces_for_user(user.id)])


def first_workspace_id(repo: AuthRepository, user: UserModel | None) -> str | None:
    if user is None:
        return None
    memberships = repo.list_workspaces_for_user(user.id)
    return memberships[0].workspace_id if memberships else None


@router.post("/register", response_model=AuthResult, status_code=status.HTTP_201_CREATED, summary="Register a user")
def register(
    payload: RegisterRequest,
    response: Response,
    request: Request,
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResult:
    check_auth_rate_limit(request, settings, "register", settings.auth_rate_limit_register)
    if repo.get_user_by_email(payload.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    try:
        user = repo.create_user_with_workspace(payload)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc
    result = auth_result(user, repo, settings, response, request)
    AuditService(repo.db).record_auth(action=audit_actions.AUTH_LOGIN, outcome="success", user=user, workspace_id=first_workspace_id(repo, user), request=request, metadata={"registration": True})
    return result


@router.post("/login", response_model=AuthResult, summary="Login")
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResult:
    check_auth_rate_limit(request, settings, "login", settings.auth_rate_limit_login)
    user = repo.get_user_by_email(payload.email)
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        AuditService(repo.db).record_auth(action=audit_actions.AUTH_LOGIN, outcome="failure", user=user, workspace_id=first_workspace_id(repo, user), request=request, metadata={"email": payload.email})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    result = auth_result(user, repo, settings, response, request)
    AuditService(repo.db).record_auth(action=audit_actions.AUTH_LOGIN, outcome="success", user=user, workspace_id=first_workspace_id(repo, user), request=request)
    return result


@router.post("/refresh", response_model=AuthResult, summary="Rotate refresh session")
def refresh(
    response: Response,
    request: Request,
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResult:
    check_auth_rate_limit(request, settings, "refresh", settings.auth_rate_limit_refresh)
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        AuditService(repo.db).record_auth(action=audit_actions.AUTH_REFRESH_FAILED, outcome="failure", user=None, workspace_id=None, request=request, metadata={"reason": "missing"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")
    consumed = repo.consume_refresh(token, settings.refresh_token_days, request.headers.get("user-agent"))
    if consumed is None:
        AuditService(repo.db).record_auth(action=audit_actions.AUTH_REFRESH_FAILED, outcome="failure", user=None, workspace_id=None, request=request, metadata={"reason": "invalid_or_revoked"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user, new_token = consumed
    response.set_cookie(
        settings.refresh_cookie_name,
        new_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )
    return AuthResult(access_token=create_access_token(settings, user.id), user=user, workspaces=[workspace_out(item) for item in repo.list_workspaces_for_user(user.id)])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout")
def logout(
    response: Response,
    request: Request,
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    token = request.cookies.get(settings.refresh_cookie_name)
    user = repo.revoke_refresh(token) if token else None
    AuditService(repo.db).record_auth(action=audit_actions.AUTH_LOGOUT, outcome="success", user=user, workspace_id=first_workspace_id(repo, user), request=request)
    response.delete_cookie(settings.refresh_cookie_name, path="/api/v1/auth")


@router.get("/me", response_model=AuthResult, summary="Current user")
def me(
    user: Annotated[UserModel, Depends(get_current_active_user)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResult:
    return AuthResult(access_token=create_access_token(settings, user.id), user=user, workspaces=[workspace_out(item) for item in repo.list_workspaces_for_user(user.id)])
