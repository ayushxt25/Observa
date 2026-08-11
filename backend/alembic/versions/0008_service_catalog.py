"""service catalog

Revision ID: 0008_service_catalog
Revises: 0007_audit_events
Create Date: 2026-08-09 22:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_service_catalog"
down_revision: str | None = "0007_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("version", sa.String(length=80), nullable=True),
        sa.Column("owner_team", sa.String(length=120), nullable=True),
        sa.Column("repository_url", sa.String(length=500), nullable=True),
        sa.Column("runbook_url", sa.String(length=500), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_services_workspace_name"),
    )
    op.create_index("ix_services_workspace_id", "services", ["workspace_id"])
    op.create_index("ix_services_last_seen_at", "services", ["last_seen_at"])
    op.create_index("ix_services_workspace_last_seen", "services", ["workspace_id", "last_seen_at"])
    op.create_index("ix_services_workspace_environment", "services", ["workspace_id", "environment"])

    op.create_table(
        "service_dependencies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_service_id", sa.String(length=36), nullable=False),
        sa.Column("target_service_id", sa.String(length=36), nullable=False),
        sa.Column("dependency_type", sa.String(length=24), nullable=False, server_default="unknown"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_service_id <> target_service_id", name="ck_service_dependencies_not_self"),
        sa.ForeignKeyConstraint(["source_service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "source_service_id", "target_service_id", "dependency_type", name="uq_service_dependencies_workspace_edge"),
    )
    op.create_index("ix_service_dependencies_workspace_id", "service_dependencies", ["workspace_id"])
    op.create_index("ix_service_dependencies_source_service_id", "service_dependencies", ["source_service_id"])
    op.create_index("ix_service_dependencies_target_service_id", "service_dependencies", ["target_service_id"])
    op.create_index("ix_service_dependencies_workspace_source", "service_dependencies", ["workspace_id", "source_service_id"])
    op.create_index("ix_service_dependencies_workspace_target", "service_dependencies", ["workspace_id", "target_service_id"])


def downgrade() -> None:
    op.drop_table("service_dependencies")
    op.drop_table("services")
