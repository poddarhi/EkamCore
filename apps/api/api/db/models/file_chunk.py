from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.models.base import Base


class FileChunk(Base):
    __tablename__ = "file_chunks"

    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(10), nullable=False)
    embedding_id: Mapped[str | None] = mapped_column(String(100))

    file = relationship("File", back_populates="chunks", lazy="selectin")
