from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.models.base import Base


class File(Base):
    __tablename__ = "files"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    duplicate_of_id: Mapped[UUID | None] = mapped_column(ForeignKey("files.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source = relationship("Source", back_populates="files", lazy="selectin")
    chunks = relationship("FileChunk", back_populates="file", lazy="noload", cascade="all, delete-orphan")
    ingestion_state = relationship("IngestionState", back_populates="file", uselist=False, lazy="selectin")
    duplicate_of = relationship("File", remote_side="File.id", lazy="noload")
