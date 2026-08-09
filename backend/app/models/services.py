from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ServiceCatalogModel(Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_services_workspace_name"),
        Index("ix_services_workspace_last_seen", "workspace_id", "last_seen_at"),
        Index("ix_services_workspace_environment", "workspace_id", "environment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(String(64), index=True)
    version: Mapped[str | None] = mapped_column(String(80))
    owner_team: Mapped[str | None] = mapped_column(String(120))
    repository_url: Mapped[str | None] = mapped_column(String(500))
    runbook_url: Mapped[str | None] = mapped_column(String(500))
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    outgoing_dependencies: Mapped[list["ServiceDependencyModel"]] = relationship(
        foreign_keys="ServiceDependencyModel.source_service_id",
        back_populates="source_service",
        cascade="all, delete-orphan",
    )
    incoming_dependencies: Mapped[list["ServiceDependencyModel"]] = relationship(
        foreign_keys="ServiceDependencyModel.target_service_id",
        back_populates="target_service",
        cascade="all, delete-orphan",
    )


class ServiceDependencyModel(Base):
    __tablename__ = "service_dependencies"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source_service_id", "target_service_id", "dependency_type", name="uq_service_dependencies_workspace_edge"),
        CheckConstraint("source_service_id <> target_service_id", name="ck_service_dependencies_not_self"),
        Index("ix_service_dependencies_workspace_source", "workspace_id", "source_service_id"),
        Index("ix_service_dependencies_workspace_target", "workspace_id", "target_service_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    source_service_id: Mapped[str] = mapped_column(String(36), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    target_service_id: Mapped[str] = mapped_column(String(36), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    dependency_type: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    source_service: Mapped[ServiceCatalogModel] = relationship(foreign_keys=[source_service_id], back_populates="outgoing_dependencies")
    target_service: Mapped[ServiceCatalogModel] = relationship(foreign_keys=[target_service_id], back_populates="incoming_dependencies")
