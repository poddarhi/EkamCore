"""Photo metadata search service (S08-002).

Filters on direct columns of photo_assets — no JSONB queries needed.
All string filters use ILIKE for case-insensitive partial matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.photo_asset import PhotoAsset
from api.schemas.envelope import PhotoCard

logger = structlog.get_logger()


@dataclass(frozen=True)
class PhotoFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    location_contains: str | None = None    # ILIKE on location_name
    camera: str | None = None               # ILIKE on camera_make OR camera_model separately
    has_gps: bool | None = None


def _build_filters(
    workspace_ids: list[UUID],
    query: str,
    filters: PhotoFilters,
):
    """Build a list of SQLAlchemy filter clauses."""
    # These two are unconditional — clauses is never empty going into and_(*clauses).
    # and_() with zero args produces true(), which would bypass workspace isolation.
    clauses = [
        PhotoAsset.workspace_id.in_(workspace_ids),
        PhotoAsset.deleted_at.is_(None),
    ]

    if filters.date_from is not None:
        clauses.append(PhotoAsset.taken_at >= filters.date_from)
    if filters.date_to is not None:
        clauses.append(PhotoAsset.taken_at <= filters.date_to)
    if filters.location_contains:
        clauses.append(PhotoAsset.location_name.ilike(f"%{filters.location_contains}%"))
    if filters.camera:
        cam_like = f"%{filters.camera}%"
        clauses.append(
            or_(
                PhotoAsset.camera_make.ilike(cam_like),
                PhotoAsset.camera_model.ilike(cam_like),
            )
        )
    if filters.has_gps is True:
        clauses.append(PhotoAsset.gps_lat.isnot(None))
    elif filters.has_gps is False:
        clauses.append(PhotoAsset.gps_lat.is_(None))

    if query:
        q_like = f"%{query}%"
        clauses.append(
            or_(
                PhotoAsset.location_name.ilike(q_like),
                PhotoAsset.camera_make.ilike(q_like),
                PhotoAsset.camera_model.ilike(q_like),
            )
        )

    return clauses


def _photo_to_card(photo: PhotoAsset) -> PhotoCard:
    camera_parts = [p for p in [photo.camera_make, photo.camera_model] if p]
    camera = " ".join(camera_parts).strip() or None
    return PhotoCard(
        id=photo.id,
        priority_score=0.7,
        source_ids=[photo.file_id],
        payload={
            "photo_id": str(photo.id),
            "thumbnail_url": f"/api/v1/photos/{photo.id}/thumbnail",
            "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
            "location_name": photo.location_name,
            "camera": camera,
            "width": photo.width,
            "height": photo.height,
        },
    )


async def search_photos(
    workspace_ids: list[UUID],
    query: str,
    filters: PhotoFilters,
    limit: int,
    offset: int,
    db: AsyncSession,
) -> tuple[list[PhotoCard], int]:
    """Search photo_assets by metadata filters and free-text query.

    Returns (cards, total_count).  Cards are ordered taken_at DESC.
    """
    clauses = _build_filters(workspace_ids, query, filters)

    stmt = (
        select(PhotoAsset)
        .where(and_(*clauses))
        .order_by(PhotoAsset.taken_at.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    photos = result.scalars().all()

    count_stmt = (
        select(func.count())
        .select_from(PhotoAsset)
        .where(and_(*clauses))
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return [_photo_to_card(p) for p in photos], total
