"""Face pipeline status endpoint (S11-008).

GET /api/v1/face/status — per-workspace aggregate of face pipeline state
for the authenticated user's workspace. Consumed by the Photo
Intelligence settings page to render "State B" counts without poking
at raw DB tables from the frontend.

Consent enforcement: mirrors face_consent.py — we derive the workspace
from the authenticated user and check consent inline. We deliberately
do NOT use the ``require_face_consent`` dependency here because that
dependency takes workspace_id from a query parameter, which opens a
confused-deputy vector — the user would be able to ask "what is the
face status of workspace X?" for any X they once had access to. The
user-derived approach matches the existing consent API.

Privacy rules (ART-14 §4):
  - No bbox coordinates, no embeddings, no filenames in the response
  - Only counts, timestamps, and version strings
  - Workspace ID is included so the caller can verify they asked about
    the right workspace (guards against confused deputy via frontend bug)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_backfill_job import FaceBackfillJob
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.photo_asset import PhotoAsset
from api.db.session import get_db
from api.errors import AuthorizationError, FaceConsentRequiredError
from api.middleware.auth import get_current_user
from api.schemas.auth import CurrentUser
from api.services.face import consent_service
from api.services.face.face_config import (
    DETECTOR_VERSION,
    RECOGNIZER_VERSION,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/face", tags=["face-status"])


# ── Response models ────────────────────────────────────────────────────────


class ConsentSummary(BaseModel):
    accepted: bool
    version: str | None = None
    granted_at: datetime | None = None


class ModelSummary(BaseModel):
    detector_version: str
    recognizer_version: str


class BackfillSummary(BaseModel):
    state: str  # "running" | "completed" | "failed" | "cancelled" | "none"
    progress: str  # "<processed>/<total>", or "" when state == "none"


class FaceStatusResponse(BaseModel):
    workspace_id: UUID
    consent: ConsentSummary
    face_count: int
    cluster_count: int
    photos_with_faces: int
    photos_without_faces: int
    photos_unprocessed: int
    last_processed_at: datetime | None = None
    model: ModelSummary
    backfill: BackfillSummary


# ── Helpers ────────────────────────────────────────────────────────────────


def _resolve_workspace(user: CurrentUser) -> UUID:
    if not user.workspace_ids:
        raise AuthorizationError(
            error_code="NO_WORKSPACE",
            message="User has no workspace.",
        )
    return user.workspace_ids[0]


async def _require_consent(workspace_id: UUID, db: AsyncSession) -> None:
    if not await consent_service.is_consent_active(workspace_id, db):
        raise FaceConsentRequiredError(
            error_code="FACE_CONSENT_REQUIRED",
            message=(
                "Face clustering requires your explicit consent. "
                "Enable it in Settings \u2192 Photo Intelligence."
            ),
        )


# ── GET /api/v1/face/status ────────────────────────────────────────────────


@router.get("/status", response_model=FaceStatusResponse)
async def get_face_status(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FaceStatusResponse:
    """Return the face pipeline status for the caller's workspace.

    Requires active consent. All fields are aggregate — no per-photo
    or per-face detail leaks.
    """
    workspace_id = _resolve_workspace(user)
    await _require_consent(workspace_id, db)

    consent_record = await consent_service.get_active_consent(
        workspace_id, db
    )

    # ── Counts ────────────────────────────────────────────────────────────
    face_count = int(
        (
            await db.execute(
                select(func.count(FaceDetection.id)).where(
                    and_(
                        FaceDetection.workspace_id == workspace_id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        ).scalar_one()
    )
    cluster_count = int(
        (
            await db.execute(
                select(func.count(FaceCluster.id)).where(
                    and_(
                        FaceCluster.workspace_id == workspace_id,
                        FaceCluster.deleted_at.is_(None),
                    )
                )
            )
        ).scalar_one()
    )

    # Use face_processed_at (S11-007) to split processed vs. unprocessed.
    # face_count=0 alone is ambiguous — could mean "never processed" or
    # "processed, zero faces found". face_processed_at is the explicit
    # "we ran detection against this photo" marker.
    photos_with_faces = int(
        (
            await db.execute(
                select(func.count(PhotoAsset.id)).where(
                    and_(
                        PhotoAsset.workspace_id == workspace_id,
                        PhotoAsset.deleted_at.is_(None),
                        PhotoAsset.face_processed_at.isnot(None),
                        PhotoAsset.face_count > 0,
                    )
                )
            )
        ).scalar_one()
    )
    photos_without_faces = int(
        (
            await db.execute(
                select(func.count(PhotoAsset.id)).where(
                    and_(
                        PhotoAsset.workspace_id == workspace_id,
                        PhotoAsset.deleted_at.is_(None),
                        PhotoAsset.face_processed_at.isnot(None),
                        PhotoAsset.face_count == 0,
                    )
                )
            )
        ).scalar_one()
    )
    photos_unprocessed = int(
        (
            await db.execute(
                select(func.count(PhotoAsset.id)).where(
                    and_(
                        PhotoAsset.workspace_id == workspace_id,
                        PhotoAsset.deleted_at.is_(None),
                        PhotoAsset.face_processed_at.is_(None),
                    )
                )
            )
        ).scalar_one()
    )

    last_processed_at: datetime | None = (
        await db.execute(
            select(func.max(FaceDetection.created_at)).where(
                and_(
                    FaceDetection.workspace_id == workspace_id,
                    FaceDetection.deleted_at.is_(None),
                )
            )
        )
    ).scalar()

    # ── Latest backfill ───────────────────────────────────────────────────
    latest_job = (
        await db.execute(
            select(FaceBackfillJob)
            .where(FaceBackfillJob.workspace_id == workspace_id)
            .order_by(FaceBackfillJob.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if latest_job is None:
        backfill = BackfillSummary(state="none", progress="")
    else:
        backfill = BackfillSummary(
            state=latest_job.state,
            progress=f"{latest_job.processed_photos}/{latest_job.total_photos}",
        )

    return FaceStatusResponse(
        workspace_id=workspace_id,
        consent=ConsentSummary(
            accepted=True,
            version=consent_record.version if consent_record else None,
            granted_at=(
                consent_record.granted_at if consent_record else None
            ),
        ),
        face_count=face_count,
        cluster_count=cluster_count,
        photos_with_faces=photos_with_faces,
        photos_without_faces=photos_without_faces,
        photos_unprocessed=photos_unprocessed,
        last_processed_at=last_processed_at,
        model=ModelSummary(
            detector_version=DETECTOR_VERSION,
            recognizer_version=RECOGNIZER_VERSION,
        ),
        backfill=backfill,
    )
