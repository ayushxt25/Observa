from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelemetryEventModel(Base):
    __tablename__ = "telemetry_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_telemetry_events_workspace_event_id"),
        Index("ix_telemetry_events_workspace_timestamp", "workspace_id", "timestamp"),
        Index("ix_telemetry_events_workspace_service_timestamp", "workspace_id", "service", "timestamp"),
        Index("ix_telemetry_events_workspace_region_timestamp", "workspace_id", "region", "timestamp"),
    )

    db_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    id: Mapped[str] = mapped_column(String(80), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    latency: Mapped[float] = mapped_column(Float, nullable=False)
    throughput: Mapped[float] = mapped_column(Float, nullable=False)
    cpu_usage: Mapped[float] = mapped_column(Float, nullable=False)
    memory_usage: Mapped[float] = mapped_column(Float, nullable=False)
    error_rate: Mapped[float] = mapped_column(Float, nullable=False)
    payload_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
