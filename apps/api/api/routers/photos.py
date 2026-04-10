"""Photo asset endpoints (S08-001).

GET /api/v1/photos/{id}           — photo metadata card
GET /api/v1/photos/{id}/thumbnail — JPEG thumbnail bytes
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import anyio

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db.models.photo_asset import PhotoAsset
from api.db.session import get_db
from api.errors import NotFoundError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.schemas.envelope import PhotoCard

logger = structlog.get_logger()

_FLAG = require_flag("photos_enabled")

router = APIRouter(prefix="/api/v1/photos", tags=["photos"])


def _photo_to_card(photo: PhotoAsset) -> PhotoCard:
    camera = " ".join(p for p in [photo.camera_make, photo.camera_model] if p).strip() or None
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


@router.get("/{photo_id}", dependencies=[_FLAG])
async def get_photo(
    photo_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(PhotoAsset).where(
        and_(
            PhotoAsset.id == photo_id,
            PhotoAsset.workspace_id.in_(user.workspace_ids),
            PhotoAsset.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    photo = result.scalar_one_or_none()
    if photo is None:
        raise NotFoundError(error_code="PHOTO_NOT_FOUND", message="Photo not found.")
    return _photo_to_card(photo).model_dump()


@router.get("/{photo_id}/thumbnail", dependencies=[_FLAG])
async def get_photo_thumbnail(
    photo_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    stmt = select(PhotoAsset).where(
        and_(
            PhotoAsset.id == photo_id,
            PhotoAsset.workspace_id.in_(user.workspace_ids),
            PhotoAsset.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    photo = result.scalar_one_or_none()
    if photo is None:
        raise NotFoundError(error_code="PHOTO_NOT_FOUND", message="Photo not found.")
    if not photo.thumbnail_path:
        raise NotFoundError(error_code="THUMBNAIL_NOT_FOUND", message="Thumbnail not yet generated.")

    thumb_path = anyio.Path(settings.THUMBNAIL_DIR) / photo.thumbnail_path
    if not await thumb_path.exists():
        raise NotFoundError(error_code="THUMBNAIL_NOT_FOUND", message="Thumbnail file missing.")

    return Response(
        content=await thumb_path.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )
