"""Photo asset endpoints (S08-001 / S13-008).

GET /api/v1/photos/{id}            — photo metadata card
GET /api/v1/photos/{id}/thumbnail  — JPEG thumbnail bytes
GET /api/v1/photos/{id}/full       — full-resolution JPEG bytes (S13-008)
GET /api/v1/photos/{id}/faces      — per-photo face list with person linkage
                                     for the lightbox overlay (S13-008)
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
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.trusted_person import TrustedPerson
from api.db.session import get_db
from api.errors import NotFoundError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.schemas.envelope import PhotoCard
from api.schemas.photo_faces import PhotoFaceItem, PhotoFacesResponse
from api.services.face import consent_service

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


# ── S13-008: full-resolution image + face overlay ────────────────────────


@router.get("/{photo_id}/full", dependencies=[_FLAG])
async def get_photo_full(
    photo_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the full-resolution image bytes for the lightbox.

    Reads the underlying file's ``path`` from disk. Only JPEG is
    served — HEIC (iCloud default) would need Pillow-HEIF transcoding,
    which is out of scope for v1. Callers that get
    ``PHOTO_UNSUPPORTED_FORMAT`` should fall back to the thumbnail.
    """
    row = (
        await db.execute(
            select(PhotoAsset, File.path, File.mime_type)
            .join(File, File.id == PhotoAsset.file_id)
            .where(
                and_(
                    PhotoAsset.id == photo_id,
                    PhotoAsset.workspace_id.in_(user.workspace_ids),
                    PhotoAsset.deleted_at.is_(None),
                    File.deleted_at.is_(None),
                )
            )
        )
    ).first()
    if row is None:
        raise NotFoundError(
            error_code="PHOTO_NOT_FOUND",
            message="Photo not found.",
        )
    _photo, path, mime = row
    if mime not in ("image/jpeg", "image/jpg", None):
        raise NotFoundError(
            error_code="PHOTO_UNSUPPORTED_FORMAT",
            message="Full-resolution bytes are only served for JPEG.",
        )
    file_path = anyio.Path(path)
    if not await file_path.exists():
        raise NotFoundError(
            error_code="PHOTO_FILE_MISSING",
            message="Underlying image file is missing from disk.",
        )
    return Response(
        content=await file_path.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/{photo_id}/faces", response_model=PhotoFacesResponse)
async def get_photo_faces(
    photo_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoFacesResponse:
    """Return the face_detections for a photo plus the person linkage.

    Auth + photos_enabled + active face consent. The photos_enabled
    gate is not applied here because the caller's lightbox also
    renders photos that the photos feature flag already cleared at
    page load — we only enforce consent so face data cannot leak
    when the user has revoked it.
    """
    workspace_id = await consent_service.resolve_workspace_with_face_consent(
        user=user, db=db
    )

    # Guard the photo lookup first so a bad id returns 404 before we
    # leak face rows for a photo the user cannot see.
    photo = (
        await db.execute(
            select(PhotoAsset).where(
                and_(
                    PhotoAsset.id == photo_id,
                    PhotoAsset.workspace_id == workspace_id,
                    PhotoAsset.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if photo is None:
        raise NotFoundError(
            error_code="PHOTO_NOT_FOUND",
            message="Photo not found.",
        )

    rows = (
        await db.execute(
            select(
                FaceDetection.id,
                FaceDetection.bbox_json,
                FaceDetection.detection_score,
                FaceDetection.cluster_id,
                FaceCluster.trusted_person_id,
                TrustedPerson.display_name,
            )
            .select_from(FaceDetection)
            .outerjoin(FaceCluster, FaceCluster.id == FaceDetection.cluster_id)
            .outerjoin(
                TrustedPerson,
                TrustedPerson.id == FaceCluster.trusted_person_id,
            )
            .where(
                and_(
                    FaceDetection.photo_asset_id == photo_id,
                    FaceDetection.workspace_id == workspace_id,
                    FaceDetection.deleted_at.is_(None),
                )
            )
            .order_by(FaceDetection.detection_score.desc())
        )
    ).all()

    items: list[PhotoFaceItem] = []
    for r in rows:
        person_id = r.trusted_person_id
        items.append(
            PhotoFaceItem(
                face_detection_id=r.id,
                bbox=r.bbox_json or {},
                detection_score=r.detection_score,
                cluster_id=r.cluster_id,
                trusted_person_id=person_id,
                trusted_person_display_name=r.display_name,
                trusted_person_avatar_url=(
                    f"/api/v1/people/{person_id}/avatar"
                    if person_id is not None
                    else None
                ),
            )
        )
    return PhotoFacesResponse(items=items)
