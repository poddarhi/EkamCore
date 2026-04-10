from datetime import datetime
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base

# Valid values for the status column.
CANDIDATE_STATUS_PENDING = "pending"
CANDIDATE_STATUS_CONFIRMED = "confirmed"
CANDIDATE_STATUS_REJECTED = "rejected"


class CorrespondentContactCandidate(Base):
    """Fuzzy-match candidates between Paperless correspondents and EkamCore contacts.

    One row per (workspace_id, paperless_correspondent_id).  The bridge
    service upserts rows on each run; rows with status 'confirmed' or
    'rejected' are never overwritten so human review decisions are preserved.

    contact_id is NULL when no contact reached MATCH_THRESHOLD — the row
    still records that the correspondent was processed.
    """

    __tablename__ = "correspondent_contact_candidates"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "paperless_correspondent_id",
            name="uq_ccc_workspace_correspondent",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    paperless_correspondent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    paperless_correspondent_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id"), nullable=True, index=True
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CANDIDATE_STATUS_PENDING
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
