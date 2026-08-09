from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class NotificationChannelModel(Base):
    __tablename__ = "notification_channels"
    __table_args__ = (
        Index("ix_notification_channels_workspace_created", "workspace_id", "created_at"),
        Index("ix_notification_channels_workspace_type", "workspace_id", "type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deliveries: Mapped[list["NotificationDeliveryModel"]] = relationship(back_populates="channel")


class AlertNotificationChannelModel(Base):
    __tablename__ = "alert_notification_channels"
    __table_args__ = (
        UniqueConstraint("alert_rule_id", "channel_id", name="uq_alert_notification_channels_rule_channel"),
        Index("ix_alert_notification_channels_workspace_rule", "workspace_id", "alert_rule_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class NotificationDeliveryModel(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("incident_id", "channel_id", "event_type", name="uq_notification_deliveries_incident_channel_event"),
        Index("ix_notification_deliveries_workspace_status_retry", "workspace_id", "status", "next_retry_at"),
        Index("ix_notification_deliveries_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("alert_rules.id", ondelete="CASCADE"), index=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("notification_channels.id", ondelete="SET NULL"), index=True)
    channel_name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(16), nullable=False)
    channel_config_json: Mapped[str] = mapped_column(Text, nullable=False)
    channel_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    response_code: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[NotificationChannelModel | None] = relationship(back_populates="deliveries")
