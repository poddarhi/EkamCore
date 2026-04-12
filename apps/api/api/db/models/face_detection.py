"""Face detection ORM model (S11-001 / ART-11).

One row per detected face. Embedding is application-encrypted (Fernet).
qdrant_point_id UUID matches the point ID in Qdrant face_embeddings.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class FaceDetection(Base):
    __tablename__ = "face_detections"
    __table_args__ = (
        UniqueConstraint("qdrant_point_id", name="uq_face_detections_qdrant_point_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    photo_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("photo_assets.id", ondelete="CASCADE"), nullable=False
    )
    bbox_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    embedding_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    embedding_dim: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("512")
    )
    detector_version: Mapped[str] = mapped_column(String(64), nullable=False)
    recognizer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    cluster_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("face_clusters.id", ondelete="SET NULL"), nullable=True
    )
    detection_score: Mapped[float] = mapped_column(Float, nullable=False)
    qdrant_point_id: Mapped[UUID] = mapped_column(nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
