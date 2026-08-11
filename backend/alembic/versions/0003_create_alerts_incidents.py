"""create alerts and incidents

Revision ID: 0003_create_alerts_incidents
Revises: 0002_create_dashboards
Create Date: 2026-08-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003_create_alerts_incidents"
down_revision: str | None = "0002_create_dashboards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("aggregation", sa.String(length=16), nullable=False),
        sa.Column("bucket", sa.String(length=16), nullable=False),
        sa.Column("evaluation_window_seconds", sa.Integer(), nullable=False),
        sa.Column("operator", sa.String(length=2), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("evaluation_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("evaluation_interval_seconds >= 5", name="ck_alert_rules_evaluation_interval_min"),
        sa.CheckConstraint("cooldown_seconds >= 0", name="ck_alert_rules_cooldown_non_negative"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_rules")),
    )
    op.create_index("ix_alert_rules_enabled_due", "alert_rules", ["enabled", "last_evaluated_at"])
    op.create_index("ix_alert_rules_metric_service", "alert_rules", ["metric", "service"])
    op.create_index(op.f("ix_alert_rules_enabled"), "alert_rules", ["enabled"])
    op.create_index(op.f("ix_alert_rules_name"), "alert_rules", ["name"])
    op.create_index(op.f("ix_alert_rules_region"), "alert_rules", ["region"])
    op.create_index(op.f("ix_alert_rules_service"), "alert_rules", ["service"])
    op.create_index(op.f("ix_alert_rules_state"), "alert_rules", ["state"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("alert_rule_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggering_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["alert_rule_id"], ["alert_rules.id"], name=op.f("fk_incidents_alert_rule_id_alert_rules"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index("ix_incidents_opened_status", "incidents", ["status", "opened_at"])
    op.create_index("ix_incidents_rule_status", "incidents", ["alert_rule_id", "status"])
    op.create_index(op.f("ix_incidents_alert_rule_id"), "incidents", ["alert_rule_id"])
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"])
    op.create_index(
        "uq_incidents_one_firing_per_rule",
        "incidents",
        ["alert_rule_id"],
        unique=True,
        postgresql_where=sa.text("status = 'firing'"),
    )


def downgrade() -> None:
    op.drop_index("uq_incidents_one_firing_per_rule", table_name="incidents")
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_alert_rule_id"), table_name="incidents")
    op.drop_index("ix_incidents_rule_status", table_name="incidents")
    op.drop_index("ix_incidents_opened_status", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index(op.f("ix_alert_rules_state"), table_name="alert_rules")
    op.drop_index(op.f("ix_alert_rules_service"), table_name="alert_rules")
    op.drop_index(op.f("ix_alert_rules_region"), table_name="alert_rules")
    op.drop_index(op.f("ix_alert_rules_name"), table_name="alert_rules")
    op.drop_index(op.f("ix_alert_rules_enabled"), table_name="alert_rules")
    op.drop_index("ix_alert_rules_metric_service", table_name="alert_rules")
    op.drop_index("ix_alert_rules_enabled_due", table_name="alert_rules")
    op.drop_table("alert_rules")
