"""notifications

Revision ID: 0006_notifications
Revises: 0005_telemetry_tenancy
Create Date: 2026-08-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_notifications"
down_revision: str | None = "0005_telemetry_tenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_notification_channels_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_channels")),
    )
    op.create_index(op.f("ix_notification_channels_enabled"), "notification_channels", ["enabled"])
    op.create_index(op.f("ix_notification_channels_workspace_id"), "notification_channels", ["workspace_id"])
    op.create_index("ix_notification_channels_workspace_created", "notification_channels", ["workspace_id", "created_at"])
    op.create_index("ix_notification_channels_workspace_type", "notification_channels", ["workspace_id", "type"])

    op.create_table(
        "alert_notification_channels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("alert_rule_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["alert_rule_id"], ["alert_rules.id"], name=op.f("fk_alert_notification_channels_alert_rule_id_alert_rules"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["notification_channels.id"], name=op.f("fk_alert_notification_channels_channel_id_notification_channels"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_alert_notification_channels_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_notification_channels")),
        sa.UniqueConstraint("alert_rule_id", "channel_id", name="uq_alert_notification_channels_rule_channel"),
    )
    op.create_index(op.f("ix_alert_notification_channels_alert_rule_id"), "alert_notification_channels", ["alert_rule_id"])
    op.create_index(op.f("ix_alert_notification_channels_channel_id"), "alert_notification_channels", ["channel_id"])
    op.create_index(op.f("ix_alert_notification_channels_workspace_id"), "alert_notification_channels", ["workspace_id"])
    op.create_index("ix_alert_notification_channels_workspace_rule", "alert_notification_channels", ["workspace_id", "alert_rule_id"])

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("alert_rule_id", sa.String(length=36), nullable=True),
        sa.Column("incident_id", sa.String(length=36), nullable=True),
        sa.Column("channel_id", sa.String(length=36), nullable=True),
        sa.Column("channel_name", sa.String(length=120), nullable=False),
        sa.Column("channel_type", sa.String(length=16), nullable=False),
        sa.Column("channel_config_json", sa.Text(), nullable=False),
        sa.Column("channel_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["alert_rule_id"], ["alert_rules.id"], name=op.f("fk_notification_deliveries_alert_rule_id_alert_rules"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["notification_channels.id"], name=op.f("fk_notification_deliveries_channel_id_notification_channels"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], name=op.f("fk_notification_deliveries_incident_id_incidents"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_notification_deliveries_workspace_id_workspaces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint("incident_id", "channel_id", "event_type", name="uq_notification_deliveries_incident_channel_event"),
    )
    op.create_index(op.f("ix_notification_deliveries_alert_rule_id"), "notification_deliveries", ["alert_rule_id"])
    op.create_index(op.f("ix_notification_deliveries_channel_id"), "notification_deliveries", ["channel_id"])
    op.create_index(op.f("ix_notification_deliveries_created_at"), "notification_deliveries", ["created_at"])
    op.create_index(op.f("ix_notification_deliveries_incident_id"), "notification_deliveries", ["incident_id"])
    op.create_index(op.f("ix_notification_deliveries_next_retry_at"), "notification_deliveries", ["next_retry_at"])
    op.create_index(op.f("ix_notification_deliveries_status"), "notification_deliveries", ["status"])
    op.create_index(op.f("ix_notification_deliveries_workspace_id"), "notification_deliveries", ["workspace_id"])
    op.create_index("ix_notification_deliveries_workspace_created", "notification_deliveries", ["workspace_id", "created_at"])
    op.create_index("ix_notification_deliveries_status_attempt", "notification_deliveries", ["status", "last_attempt_at"])
    op.create_index("ix_notification_deliveries_workspace_status_retry", "notification_deliveries", ["workspace_id", "status", "next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_workspace_status_retry", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_status_attempt", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_workspace_created", table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_workspace_id"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_status"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_next_retry_at"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_incident_id"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_created_at"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_channel_id"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_alert_rule_id"), table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("ix_alert_notification_channels_workspace_rule", table_name="alert_notification_channels")
    op.drop_index(op.f("ix_alert_notification_channels_workspace_id"), table_name="alert_notification_channels")
    op.drop_index(op.f("ix_alert_notification_channels_channel_id"), table_name="alert_notification_channels")
    op.drop_index(op.f("ix_alert_notification_channels_alert_rule_id"), table_name="alert_notification_channels")
    op.drop_table("alert_notification_channels")
    op.drop_index("ix_notification_channels_workspace_type", table_name="notification_channels")
    op.drop_index("ix_notification_channels_workspace_created", table_name="notification_channels")
    op.drop_index(op.f("ix_notification_channels_workspace_id"), table_name="notification_channels")
    op.drop_index(op.f("ix_notification_channels_enabled"), table_name="notification_channels")
    op.drop_table("notification_channels")
