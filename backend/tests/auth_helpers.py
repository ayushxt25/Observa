from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.auth import UserModel, WorkspaceMembershipModel, WorkspaceModel


def authenticate_test_client(client: TestClient, db: Session, role: str = "owner") -> str:
    user = UserModel(email="owner@example.com", password_hash=hash_password("test-password-123"), display_name="Owner")
    workspace = WorkspaceModel(name="Test Workspace", slug="test-workspace")
    db.add_all([user, workspace])
    db.flush()
    db.add(WorkspaceMembershipModel(user_id=user.id, workspace_id=workspace.id, role=role))
    db.commit()
    client.headers.update({
        "Authorization": f"Bearer {create_access_token(get_settings(), user.id)}",
        "X-Workspace-Id": workspace.id,
    })
    return workspace.id
