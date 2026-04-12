"""Face backfill job ORM model (S11-007).

One row per user-initiated backfill run. Tracks totals, progress, terminal
state, and an optional error message so the UI can poll for progress and
display the correct final state without re-computing anything in the
frontend.

State machine:
    running  ──► completed   (normal finish)
            ──► failed       (unrecoverable error during worker run)
            ──► cancelled    (user cancelled OR consent revoked mid-run)
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class FaceBackfillJob(Base):
    __tablename__ = "face_backfill_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running', 'completed', 'failed', 'cancelled')",
            name="ck_face_backfill_jobs_state",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_photos: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_photos: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failed_photos: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'running'")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
