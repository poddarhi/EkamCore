"""Person operation ORM — undo log row (S12-006)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class PersonOperation(Base):
    __tablename__ = "person_operations"

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    forward_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    inverse_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    undone_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
