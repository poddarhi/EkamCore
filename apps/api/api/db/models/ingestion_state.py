from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.models.base import Base


class IngestionState(Base):
    __tablename__ = "ingestion_states"

    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), unique=True, nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    current_stage: Mapped[str] = mapped_column(String(30), server_default="DISCOVERED", nullable=False)
    stages_completed: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)

    file = relationship("File", back_populates="ingestion_state", lazy="selectin")
