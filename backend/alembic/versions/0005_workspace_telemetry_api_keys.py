"""workspace telemetry api keys

Revision ID: 0005_telemetry_tenancy
Revises: 0004_auth_workspaces_rbac
Create Date: 2026-08-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_telemetry_tenancy"
down_revision: str | None = "0004_auth_workspaces_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-4000-8000-000000000002"


def upgrade() -> None:
    op.create_table(
        "workspace_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_workspace_api_keys_created_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_workspace_api_keys_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_api_keys")),
    )
    op.create_index(op.f("ix_workspace_api_keys_created_by_user_id"), "workspace_api_keys", ["created_by_user_id"])
    op.create_index(op.f("ix_workspace_api_keys_expires_at"), "workspace_api_keys", ["expires_at"])
    op.create_index(op.f("ix_workspace_api_keys_key_hash"), "workspace_api_keys", ["key_hash"], unique=True)
    op.create_index(op.f("ix_workspace_api_keys_key_prefix"), "workspace_api_keys", ["key_prefix"], unique=True)
    op.create_index(op.f("ix_workspace_api_keys_revoked_at"), "workspace_api_keys", ["revoked_at"])
    op.create_index(op.f("ix_workspace_api_keys_workspace_id"), "workspace_api_keys", ["workspace_id"])
    op.create_index("ix_workspace_api_keys_workspace_created", "workspace_api_keys", ["workspace_id", "created_at"])

    op.add_column("telemetry_events", sa.Column("workspace_id", sa.String(length=36), nullable=True))
    op.execute(sa.text("UPDATE telemetry_events SET workspace_id = :workspace_id").bindparams(workspace_id=DEFAULT_WORKSPACE_ID))
    op.alter_column("telemetry_events", "workspace_id", nullable=False)
    op.add_column("telemetry_events", sa.Column("db_id", sa.String(length=36), nullable=True))
    op.execute(sa.text("""
        UPDATE telemetry_events
        SET db_id =
            substr(md5(workspace_id || ':' || id), 1, 8) || '-' ||
            substr(md5(workspace_id || ':' || id), 9, 4) || '-' ||
            substr(md5(workspace_id || ':' || id), 13, 4) || '-' ||
            substr(md5(workspace_id || ':' || id), 17, 4) || '-' ||
            substr(md5(workspace_id || ':' || id), 21, 12)
    """))
    op.alter_column("telemetry_events", "db_id", nullable=False)
    op.drop_constraint(op.f("pk_telemetry_events"), "telemetry_events", type_="primary")
    op.create_primary_key(op.f("pk_telemetry_events"), "telemetry_events", ["db_id"])
    op.create_foreign_key(op.f("fk_telemetry_events_workspace_id_workspaces"), "telemetry_events", "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_telemetry_events_workspace_event_id", "telemetry_events", ["workspace_id", "id"])
    op.create_index(op.f("ix_telemetry_events_workspace_id"), "telemetry_events", ["workspace_id"])
    op.create_index("ix_telemetry_events_workspace_timestamp", "telemetry_events", ["workspace_id", "timestamp"])
    op.create_index("ix_telemetry_events_workspace_service_timestamp", "telemetry_events", ["workspace_id", "service", "timestamp"])
    op.create_index("ix_telemetry_events_workspace_region_timestamp", "telemetry_events", ["workspace_id", "region", "timestamp"])
    op.drop_index("ix_telemetry_events_timestamp_service", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_timestamp_region", table_name="telemetry_events")


def downgrade() -> None:
    op.drop_constraint("uq_telemetry_events_workspace_event_id", "telemetry_events", type_="unique")
    op.create_index("ix_telemetry_events_timestamp_region", "telemetry_events", ["timestamp", "region"])
    op.create_index("ix_telemetry_events_timestamp_service", "telemetry_events", ["timestamp", "service"])
    op.drop_index("ix_telemetry_events_workspace_region_timestamp", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_workspace_service_timestamp", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_workspace_timestamp", table_name="telemetry_events")
    op.drop_index(op.f("ix_telemetry_events_workspace_id"), table_name="telemetry_events")
    op.drop_constraint(op.f("fk_telemetry_events_workspace_id_workspaces"), "telemetry_events", type_="foreignkey")
    op.drop_constraint(op.f("pk_telemetry_events"), "telemetry_events", type_="primary")
    op.create_primary_key(op.f("pk_telemetry_events"), "telemetry_events", ["id"])
    op.drop_column("telemetry_events", "db_id")
    op.drop_column("telemetry_events", "workspace_id")
    op.drop_index("ix_workspace_api_keys_workspace_created", table_name="workspace_api_keys")
    op.drop_index(op.f("ix_workspace_api_keys_workspace_id"), table_name="workspace_api_keys")
    op.drop_index(op.f("ix_workspace_api_keys_revoked_at"), table_name="workspace_api_keys")
    op.drop_index(op.f("ix_workspace_api_keys_key_prefix"), table_name="workspace_api_keys")
    op.drop_index(op.f("ix_workspace_api_keys_key_hash"), table_name="workspace_api_keys")
    op.drop_index(op.f("ix_workspace_api_keys_expires_at"), table_name="workspace_api_keys")
    op.drop_index(op.f("ix_workspace_api_keys_created_by_user_id"), table_name="workspace_api_keys")
    op.drop_table("workspace_api_keys")
