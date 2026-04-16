"""PackRun ORM model (S14-001).

One row per pack execution. Carries the trigger, timing, outcome,
and quota counters so later stories can drive both the Today feed
banner and the ops dashboard off a single table.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class PackRun(Base):
    __tablename__ = "pack_runs"

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'running'"),
        nullable=False,
    )
    cards_produced: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    llm_calls_used: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
