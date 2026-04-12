"""Face cluster ORM model (S11-001 / ART-11).

A face_cluster groups face_detections that HDBSCAN believes belong to
the same person. Centroid is application-encrypted (Fernet).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, text
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class FaceCluster(Base):
    __tablename__ = "face_clusters"

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    centroid_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    member_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    trusted_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trusted_persons.id", ondelete="SET NULL"), nullable=True
    )
    cluster_state: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'unconfirmed'")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
