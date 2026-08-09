from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_api_key_repository, get_auth_repository, get_current_active_user, get_current_workspace, require_workspace_role
from app.core import audit_actions
from app.core.rbac import can_assign_role, can_manage_members
from app.models.auth import UserModel, WorkspaceMembershipModel
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.auth import AuthRepository
from app.schemas.api_keys import ApiKeyCreate, ApiKeyCreateResponse, ApiKeyListResponse, ApiKeyOut
from app.schemas.auth import MemberAdd, MemberPatch, MembershipListResponse, MembershipOut, WorkspaceCreate, WorkspaceListResponse, WorkspaceOut, WorkspacePatch
from app.services.audit import AuditService, changed_fields

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def workspace_out(membership: WorkspaceMembershipModel) -> WorkspaceOut:
    workspace = membership.workspace
    return WorkspaceOut(id=workspace.id, name=workspace.name, slug=workspace.slug, role=membership.role, created_at=workspace.created_at, updated_at=workspace.updated_at)


def member_out(membership: WorkspaceMembershipModel) -> MembershipOut:
    return MembershipOut(
        user_id=membership.user_id,
        email=membership.user.email,
        display_name=membership.user.display_name,
        role=membership.role,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def api_key_out(key) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        workspace_id=key.workspace_id,
        name=key.name,
        key_prefix=key.key_prefix,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        expires_at=key.expires_at,
    )


@router.get("", response_model=WorkspaceListResponse)
def list_workspaces(
    user: Annotated[UserModel, Depends(get_current_active_user)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> WorkspaceListResponse:
    return WorkspaceListResponse(workspaces=[workspace_out(item) for item in repo.list_workspaces_for_user(user.id)])


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    request: Request,
    user: Annotated[UserModel, Depends(get_current_active_user)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> WorkspaceOut:
    workspace = repo.create_workspace(user, payload.name, commit=False)
    membership = repo.get_membership(user.id, workspace.id)
    if membership is None:
        raise HTTPException(status_code=500, detail="Workspace membership was not created")
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.WORKSPACE_CREATED, resource_type="workspace", resource_id=workspace.id, request=request, metadata={"name": workspace.name, "slug": workspace.slug}, commit=False)
    repo.db.commit()
    repo.db.refresh(workspace)
    return workspace_out(membership)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: str,
    user: Annotated[UserModel, Depends(get_current_active_user)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> WorkspaceOut:
    membership = repo.get_membership(user.id, workspace_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace_out(membership)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: str,
    payload: WorkspacePatch,
    request: Request,
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("owner"))],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> WorkspaceOut:
    if membership.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    before = {"name": membership.workspace.name, "slug": membership.workspace.slug}
    repo.update_workspace(membership.workspace, payload.name, commit=False)
    after = {"name": membership.workspace.name, "slug": membership.workspace.slug}
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.WORKSPACE_UPDATED, resource_type="workspace", resource_id=workspace_id, request=request, metadata=changed_fields(before, after), commit=False)
    repo.db.commit()
    repo.db.refresh(membership.workspace)
    return workspace_out(membership)


@router.get("/{workspace_id}/members", response_model=MembershipListResponse)
def list_members(
    workspace_id: str,
    membership: Annotated[WorkspaceMembershipModel, Depends(get_current_workspace)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> MembershipListResponse:
    if membership.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    return MembershipListResponse(members=[member_out(item) for item in repo.list_members(workspace_id)])


@router.post("/{workspace_id}/members", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
def add_member(
    workspace_id: str,
    payload: MemberAdd,
    request: Request,
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> MembershipOut:
    if membership.workspace_id != workspace_id or not can_manage_members(membership.role) or not can_assign_role(membership.role, payload.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this member role")
    user = repo.get_user_by_email(payload.email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    added = repo.add_member(workspace_id, user, payload.role, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.WORKSPACE_MEMBER_ADDED, resource_type="workspace_membership", resource_id=added.id, request=request, metadata={"targetUserId": user.id, "role": added.role}, commit=False)
    repo.db.commit()
    repo.db.refresh(added)
    return member_out(added)


@router.patch("/{workspace_id}/members/{user_id}", response_model=MembershipOut)
def update_member(
    workspace_id: str,
    user_id: str,
    payload: MemberPatch,
    request: Request,
    actor: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> MembershipOut:
    if actor.workspace_id != workspace_id or not can_assign_role(actor.role, payload.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this member role")
    repo.lock_workspace_memberships(workspace_id)
    target = repo.get_membership(user_id, workspace_id, for_update=True)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if target.role == "owner" and actor.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage owner membership")
    if target.role == "owner" and payload.role != "owner" and repo.owner_count(workspace_id) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot demote final owner")
    before = {"role": target.role}
    updated = repo.update_member_role(target, payload.role, commit=False)
    AuditService(repo.db).record_user(membership=actor, action=audit_actions.WORKSPACE_MEMBER_ROLE_CHANGED, resource_type="workspace_membership", resource_id=updated.id, request=request, metadata={"targetUserId": user_id, **changed_fields(before, {"role": updated.role})}, commit=False)
    repo.db.commit()
    repo.db.refresh(updated)
    return member_out(updated)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: str,
    user_id: str,
    request: Request,
    actor: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> None:
    if actor.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    repo.lock_workspace_memberships(workspace_id)
    target = repo.get_membership(user_id, workspace_id, for_update=True)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if target.role == "owner" and actor.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage owner membership")
    if target.role == "owner" and repo.owner_count(workspace_id) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove final owner")
    target_id = target.id
    target_role = target.role
    repo.remove_member(target, commit=False)
    AuditService(repo.db).record_user(membership=actor, action=audit_actions.WORKSPACE_MEMBER_REMOVED, resource_type="workspace_membership", resource_id=target_id, request=request, metadata={"targetUserId": user_id, "role": target_role}, commit=False)
    repo.db.commit()


@router.get("/{workspace_id}/api-keys", response_model=ApiKeyListResponse)
def list_api_keys(
    workspace_id: str,
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
    repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
) -> ApiKeyListResponse:
    if membership.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    return ApiKeyListResponse(api_keys=[api_key_out(key) for key in repo.list_keys(workspace_id)])


@router.post("/{workspace_id}/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    workspace_id: str,
    payload: ApiKeyCreate,
    request: Request,
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
    repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
) -> ApiKeyCreateResponse:
    if membership.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    key, raw = repo.create_key(workspace_id, payload, membership.user_id, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.API_KEY_CREATED, resource_type="api_key", resource_id=key.id, request=request, metadata={"keyPrefix": key.key_prefix, "name": key.name, "expiresAt": key.expires_at.isoformat() if key.expires_at else None}, commit=False)
    repo.db.commit()
    repo.db.refresh(key)
    return ApiKeyCreateResponse(**api_key_out(key).model_dump(), raw_key=raw)


@router.delete("/{workspace_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    workspace_id: str,
    key_id: str,
    request: Request,
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
    repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
) -> None:
    if membership.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    key = repo.get_key(workspace_id, key_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    repo.revoke_key(key, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.API_KEY_REVOKED, resource_type="api_key", resource_id=key.id, request=request, metadata={"keyPrefix": key.key_prefix, "name": key.name}, commit=False)
    repo.db.commit()
