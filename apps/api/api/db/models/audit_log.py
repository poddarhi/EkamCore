"""ORM model for the append-only object_audit_log table."""

from uuid import UUID

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class AuditLog(Base):
    """Append-only security event log.

    Inherits created_at / updated_at from Base (both hold the insert timestamp;
    updated_at is never updated — no trigger on this table).

    The primary key is BIGSERIAL (int) instead of UUID v7 because this table is
    high-volume and append-only; sequential IDs give free cursor-based pagination.
    """

    __tablename__ = "object_audit_log"

    # Override Base's UUID primary key with BIGSERIAL
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_id: Mapped[UUID | None] = mapped_column(nullable=True)
    old_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
