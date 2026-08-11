"""create dashboards

Revision ID: 0002_create_dashboards
Revises: 0001_create_telemetry_events
Create Date: 2026-08-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_create_dashboards"
down_revision: str | None = "0001_create_telemetry_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dashboards")),
    )
    op.create_index(op.f("ix_dashboards_name"), "dashboards", ["name"], unique=False)
    op.create_table(
        "dashboard_widgets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dashboard_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=24), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("aggregation", sa.String(length=16), nullable=False),
        sa.Column("bucket", sa.String(length=16), nullable=False),
        sa.Column("time_range", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("threshold_warning", sa.Float(), nullable=True),
        sa.Column("threshold_critical", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboards.id"], name=op.f("fk_dashboard_widgets_dashboard_id_dashboards"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dashboard_widgets")),
    )
    op.create_index("ix_dashboard_widgets_dashboard_position", "dashboard_widgets", ["dashboard_id", "position"], unique=False)
    op.create_index(op.f("ix_dashboard_widgets_dashboard_id"), "dashboard_widgets", ["dashboard_id"], unique=False)
    op.create_index(op.f("ix_dashboard_widgets_region"), "dashboard_widgets", ["region"], unique=False)
    op.create_index(op.f("ix_dashboard_widgets_service"), "dashboard_widgets", ["service"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dashboard_widgets_service"), table_name="dashboard_widgets")
    op.drop_index(op.f("ix_dashboard_widgets_region"), table_name="dashboard_widgets")
    op.drop_index(op.f("ix_dashboard_widgets_dashboard_id"), table_name="dashboard_widgets")
    op.drop_index("ix_dashboard_widgets_dashboard_position", table_name="dashboard_widgets")
    op.drop_table("dashboard_widgets")
    op.drop_index(op.f("ix_dashboards_name"), table_name="dashboards")
    op.drop_table("dashboards")
