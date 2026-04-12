from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class PhotoAsset(Base):
    """Photo metadata extracted from image files.

    One-to-one with files table via file_id UNIQUE constraint.
    Created during METADATA_EXTRACTED pipeline stage.
    """

    __tablename__ = "photo_assets"
    __table_args__ = (UniqueConstraint("file_id", name="uq_photo_assets_file_id"),)

    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id"), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_make: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orientation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    exif_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    face_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # S11-007: nullable "has face detection run against this photo?" marker.
    # Populated by process_photo_for_faces on every successful run (including
    # zero-face). Cleared by hard_delete on consent revocation so backfill
    # can rediscover these photos after re-consent. NULL = never processed.
    face_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
