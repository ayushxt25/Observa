from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.telemetry import ApiModel


WorkspaceRole = Literal["owner", "admin", "member", "viewer"]


class UserOut(ApiModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceOut(ApiModel):
    id: str
    name: str
    slug: str
    role: WorkspaceRole | None = None
    created_at: datetime
    updated_at: datetime


class MembershipOut(ApiModel):
    user_id: str
    email: EmailStr
    display_name: str | None = None
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime


class AuthResult(ApiModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    workspaces: list[WorkspaceOut]


class RegisterRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    workspace_name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class WorkspaceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspacePatch(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class MemberAdd(ApiModel):
    email: EmailStr
    role: WorkspaceRole = "viewer"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class MemberPatch(ApiModel):
    role: WorkspaceRole


class WorkspaceListResponse(ApiModel):
    workspaces: list[WorkspaceOut]


class MembershipListResponse(ApiModel):
    members: list[MembershipOut]
