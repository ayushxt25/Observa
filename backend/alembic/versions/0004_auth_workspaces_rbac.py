"""auth workspaces rbac

Revision ID: 0004_auth_workspaces_rbac
Revises: 0003_create_alerts_incidents
Create Date: 2026-08-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004_auth_workspaces_rbac"
down_revision: str | None = "0003_create_alerts_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_USER_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_WORKSPACE_ID = "00000000-0000-4000-8000-000000000002"
DEFAULT_MEMBERSHIP_ID = "00000000-0000-4000-8000-000000000003"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_is_active"), "users", ["is_active"])

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_index(op.f("ix_workspaces_slug"), "workspaces", ["slug"], unique=True)

    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_workspace_memberships_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_workspace_memberships_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_memberships")),
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_workspace_memberships_user_workspace"),
    )
    op.create_index("ix_workspace_memberships_workspace_role", "workspace_memberships", ["workspace_id", "role"])
    op.create_index(op.f("ix_workspace_memberships_user_id"), "workspace_memberships", ["user_id"])
    op.create_index(op.f("ix_workspace_memberships_workspace_id"), "workspace_memberships", ["workspace_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index(op.f("ix_auth_sessions_expires_at"), "auth_sessions", ["expires_at"])
    op.create_index(op.f("ix_auth_sessions_revoked_at"), "auth_sessions", ["revoked_at"])
    op.create_index(op.f("ix_auth_sessions_token_hash"), "auth_sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"])

    users = sa.table("users", sa.column("id"), sa.column("email"), sa.column("password_hash"), sa.column("display_name"), sa.column("is_active"))
    workspaces = sa.table("workspaces", sa.column("id"), sa.column("name"), sa.column("slug"))
    memberships = sa.table("workspace_memberships", sa.column("id"), sa.column("user_id"), sa.column("workspace_id"), sa.column("role"))
    op.bulk_insert(users, [{"id": DEFAULT_USER_ID, "email": "migration-owner@example.local", "password_hash": "unusable-migration-account", "display_name": "Migration Owner", "is_active": True}])
    op.bulk_insert(workspaces, [{"id": DEFAULT_WORKSPACE_ID, "name": "Default Workspace", "slug": "default-workspace"}])
    op.bulk_insert(memberships, [{"id": DEFAULT_MEMBERSHIP_ID, "user_id": DEFAULT_USER_ID, "workspace_id": DEFAULT_WORKSPACE_ID, "role": "owner"}])

    op.add_column("dashboards", sa.Column("workspace_id", sa.String(length=36), nullable=True))
    op.execute(sa.text("UPDATE dashboards SET workspace_id = :workspace_id").bindparams(workspace_id=DEFAULT_WORKSPACE_ID))
    op.alter_column("dashboards", "workspace_id", nullable=False)
    op.create_foreign_key(op.f("fk_dashboards_workspace_id_workspaces"), "dashboards", "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_dashboards_workspace_id"), "dashboards", ["workspace_id"])
    op.create_index("ix_dashboards_workspace_updated", "dashboards", ["workspace_id", "updated_at"])

    op.add_column("alert_rules", sa.Column("workspace_id", sa.String(length=36), nullable=True))
    op.execute(sa.text("UPDATE alert_rules SET workspace_id = :workspace_id").bindparams(workspace_id=DEFAULT_WORKSPACE_ID))
    op.alter_column("alert_rules", "workspace_id", nullable=False)
    op.create_foreign_key(op.f("fk_alert_rules_workspace_id_workspaces"), "alert_rules", "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_alert_rules_workspace_id"), "alert_rules", ["workspace_id"])
    op.create_index("ix_alert_rules_workspace_created", "alert_rules", ["workspace_id", "created_at"])

    op.add_column("incidents", sa.Column("workspace_id", sa.String(length=36), nullable=True))
    op.execute(sa.text("UPDATE incidents SET workspace_id = :workspace_id").bindparams(workspace_id=DEFAULT_WORKSPACE_ID))
    op.alter_column("incidents", "workspace_id", nullable=False)
    op.create_foreign_key(op.f("fk_incidents_workspace_id_workspaces"), "incidents", "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_incidents_workspace_id"), "incidents", ["workspace_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_incidents_workspace_id"), table_name="incidents")
    op.drop_constraint(op.f("fk_incidents_workspace_id_workspaces"), "incidents", type_="foreignkey")
    op.drop_column("incidents", "workspace_id")
    op.drop_index("ix_alert_rules_workspace_created", table_name="alert_rules")
    op.drop_index(op.f("ix_alert_rules_workspace_id"), table_name="alert_rules")
    op.drop_constraint(op.f("fk_alert_rules_workspace_id_workspaces"), "alert_rules", type_="foreignkey")
    op.drop_column("alert_rules", "workspace_id")
    op.drop_index("ix_dashboards_workspace_updated", table_name="dashboards")
    op.drop_index(op.f("ix_dashboards_workspace_id"), table_name="dashboards")
    op.drop_constraint(op.f("fk_dashboards_workspace_id_workspaces"), "dashboards", type_="foreignkey")
    op.drop_column("dashboards", "workspace_id")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_token_hash"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_revoked_at"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_expires_at"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(op.f("ix_workspace_memberships_workspace_id"), table_name="workspace_memberships")
    op.drop_index(op.f("ix_workspace_memberships_user_id"), table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_workspace_role", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_index(op.f("ix_workspaces_slug"), table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
