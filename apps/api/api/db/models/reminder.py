from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.models.base import Base


class Reminder(Base):
    __tablename__ = "reminders"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    priority: Mapped[str] = mapped_column(String(10), server_default="none", nullable=False)
    list_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    write_through_status: Mapped[str] = mapped_column(String(10), server_default="pending", nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source = relationship("Source", lazy="noload")
