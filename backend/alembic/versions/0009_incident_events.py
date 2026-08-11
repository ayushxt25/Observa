"""incident timeline events

Revision ID: 0009_incident_events
Revises: 0008_service_catalog
Create Date: 2026-08-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_incident_events"
down_revision: str | None = "0008_service_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incident_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=80), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", "dedupe_key", name="uq_incident_events_incident_dedupe"),
    )
    op.create_index("ix_incident_events_workspace_id", "incident_events", ["workspace_id"])
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])
    op.create_index("ix_incident_events_event_type", "incident_events", ["event_type"])
    op.create_index("ix_incident_events_occurred_at", "incident_events", ["occurred_at"])
    op.create_index("ix_incident_events_workspace_occurred", "incident_events", ["workspace_id", "occurred_at"])
    op.create_index("ix_incident_events_incident_occurred", "incident_events", ["incident_id", "occurred_at", "id"])
    op.create_index("ix_incident_events_workspace_incident", "incident_events", ["workspace_id", "incident_id"])


def downgrade() -> None:
    op.drop_table("incident_events")
