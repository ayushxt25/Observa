from app.schemas.auth import WorkspaceRole


ROLE_RANK: dict[WorkspaceRole, int] = {
    "viewer": 0,
    "member": 1,
    "admin": 2,
    "owner": 3,
}


def has_role(current: str, minimum: WorkspaceRole) -> bool:
    return ROLE_RANK[current] >= ROLE_RANK[minimum] if current in ROLE_RANK else False


def can_manage_members(role: str) -> bool:
    return role in {"owner", "admin"}


def can_assign_role(actor_role: str, target_role: WorkspaceRole) -> bool:
    if actor_role == "owner":
        return True
    if actor_role == "admin":
        return target_role in {"viewer", "member", "admin"}
    return False
