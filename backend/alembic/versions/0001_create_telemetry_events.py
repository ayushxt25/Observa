"""create telemetry events

Revision ID: 0001_create_telemetry_events
Revises:
Create Date: 2026-08-07
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_create_telemetry_events"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("latency", sa.Float(), nullable=False),
        sa.Column("throughput", sa.Float(), nullable=False),
        sa.Column("cpu_usage", sa.Float(), nullable=False),
        sa.Column("memory_usage", sa.Float(), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("payload_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telemetry_events")),
    )
    op.create_index(op.f("ix_telemetry_events_timestamp"), "telemetry_events", ["timestamp"])
    op.create_index(op.f("ix_telemetry_events_service"), "telemetry_events", ["service"])
    op.create_index(op.f("ix_telemetry_events_region"), "telemetry_events", ["region"])
    op.create_index(op.f("ix_telemetry_events_status"), "telemetry_events", ["status"])
    op.create_index(
        "ix_telemetry_events_timestamp_service",
        "telemetry_events",
        ["timestamp", "service"],
    )
    op.create_index(
        "ix_telemetry_events_timestamp_region",
        "telemetry_events",
        ["timestamp", "region"],
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_events_timestamp_region", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_timestamp_service", table_name="telemetry_events")
    op.drop_index(op.f("ix_telemetry_events_status"), table_name="telemetry_events")
    op.drop_index(op.f("ix_telemetry_events_region"), table_name="telemetry_events")
    op.drop_index(op.f("ix_telemetry_events_service"), table_name="telemetry_events")
    op.drop_index(op.f("ix_telemetry_events_timestamp"), table_name="telemetry_events")
    op.drop_table("telemetry_events")
