"""PackCard ORM model (S14-001).

One row per card produced by a ``PackRun``. ``payload_json`` is the
pack-specific contract (follow-up suggestion, weekly summary,
relationship reminder) and is validated at the service layer —
the DB only enforces shape via the ``card_type`` CHECK constraint.

``acknowledged_*`` columns track the user's response so the Today
feed can hide acknowledged cards and the ops dashboard can report
engagement. Snoozed cards re-surface on ``snoozed_until``.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class PackCard(Base):
    __tablename__ = "pack_cards"

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    pack_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("pack_runs.id", ondelete="CASCADE"), nullable=False
    )
    card_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_action: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    snoozed_until: Mapped[date | None] = mapped_column(Date, nullable=True)
