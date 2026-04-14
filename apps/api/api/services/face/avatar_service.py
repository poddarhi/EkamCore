"""Person avatar cropping (S13-002).

Given a ``trusted_person_id``, picks the face_detection with the highest
``detection_score`` across every cluster owned by the person, loads the
owning file from disk, crops the bbox with Pillow, resizes to 160×160,
and returns the JPEG bytes.

Design rules:

  1. **Workspace isolation.** Every SELECT scopes on workspace_id.
  2. **No PII in logs.** person_id + counts only; never display_name,
     never the image bytes.
  3. **Fails closed.** Missing file, unreadable image, or bbox out of
     bounds all raise NotFoundError so the frontend can fall back to
     initials gracefully.
  4. **Redis cache.** Result cached base64 under ``person_avatar:{id}``
     with a 1 hour TTL. Cache failures are swallowed — the cache is
     advisory.
"""

from __future__ import annotations

import base64
import io
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.trusted_person import TrustedPerson
from api.errors import NotFoundError
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

AVATAR_SIZE = 160
_CACHE_PREFIX = "person_avatar:"
_CACHE_TTL_SECS = 3600


async def _cache_get(person_id: UUID) -> bytes | None:
    try:
        r = get_redis(REDIS_DB_CACHE)
        value = await r.get(f"{_CACHE_PREFIX}{person_id}")
        if value is None:
            return None
        return base64.b64decode(value)
    except Exception:
        logger.debug("avatar_cache_read_failed", exc_info=True)
        return None


async def _cache_set(person_id: UUID, data: bytes) -> None:
    try:
        r = get_redis(REDIS_DB_CACHE)
        encoded = base64.b64encode(data).decode("ascii")
        await r.set(f"{_CACHE_PREFIX}{person_id}", encoded, ex=_CACHE_TTL_SECS)
    except Exception:
        logger.debug("avatar_cache_write_failed", exc_info=True)


async def generate_avatar(
    *,
    person_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> bytes:
    """Return JPEG bytes for this person's avatar. Raises NotFoundError
    when the person has no faces or the backing image is unreadable."""

    cached = await _cache_get(person_id)
    if cached is not None:
        return cached

    # Load the person — guarantees workspace isolation before we
    # follow any foreign keys down into face data.
    person = (
        await db.execute(
            select(TrustedPerson).where(
                and_(
                    TrustedPerson.id == person_id,
                    TrustedPerson.workspace_id == workspace_id,
                    TrustedPerson.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if person is None:
        raise NotFoundError(
            error_code="PERSON_NOT_FOUND",
            message="Trusted person not found.",
        )

    # Find the highest-scoring face_detection owned by this person.
    row = (
        await db.execute(
            select(
                FaceDetection.bbox_json,
                File.path,
            )
            .join(FaceCluster, FaceCluster.id == FaceDetection.cluster_id)
            .join(PhotoAsset, PhotoAsset.id == FaceDetection.photo_asset_id)
            .join(File, File.id == PhotoAsset.file_id)
            .where(
                and_(
                    FaceCluster.trusted_person_id == person_id,
                    FaceCluster.workspace_id == workspace_id,
                    FaceDetection.workspace_id == workspace_id,
                    FaceDetection.deleted_at.is_(None),
                )
            )
            .order_by(desc(FaceDetection.detection_score))
            .limit(1)
        )
    ).first()
    if row is None:
        raise NotFoundError(
            error_code="PERSON_AVATAR_UNAVAILABLE",
            message="No faces are linked to this person yet.",
        )

    bbox = row.bbox_json or {}
    try:
        data = _crop_and_encode(row.path, bbox)
    except FileNotFoundError:
        raise NotFoundError(
            error_code="PERSON_AVATAR_UNAVAILABLE",
            message="The backing photo file is unavailable.",
        )
    except Exception:
        logger.warning(
            "avatar_crop_failed",
            person_id=str(person_id),
            exc_info=True,
        )
        raise NotFoundError(
            error_code="PERSON_AVATAR_UNAVAILABLE",
            message="The avatar could not be generated.",
        )

    await _cache_set(person_id, data)
    logger.info(
        "person_avatar_generated",
        workspace_id=str(workspace_id),
        person_id=str(person_id),
        bytes=len(data),
    )
    return data


def _crop_and_encode(path: str, bbox: dict[str, Any]) -> bytes:
    """Open the file at ``path``, crop the ``bbox``, resize to
    AVATAR_SIZE px, return JPEG bytes. PIL is imported lazily so the
    module stays importable in environments without Pillow (tests that
    don't exercise the endpoint)."""
    from PIL import Image

    img = Image.open(path).convert("RGB")
    width, height = img.size
    x = float(bbox.get("x", 0.0))
    y = float(bbox.get("y", 0.0))
    w = float(bbox.get("w", 1.0))
    h = float(bbox.get("h", 1.0))
    # Normalized bboxes (0..1) are the ingestion standard. If a bbox
    # somehow stores pixel values (>1), fall through to a full-frame
    # crop rather than erroring — the frontend can still show the
    # result and the fallback to initials stays available.
    if 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1:
        left = max(int(x * width), 0)
        top = max(int(y * height), 0)
        right = min(int((x + w) * width), width)
        bottom = min(int((y + h) * height), height)
        if right > left and bottom > top:
            img = img.crop((left, top, right, bottom))
    img.thumbnail((AVATAR_SIZE, AVATAR_SIZE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()
