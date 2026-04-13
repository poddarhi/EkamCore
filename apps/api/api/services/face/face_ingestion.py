"""Consent-gated face detection ingestion stage (S11-006).

Invoked from the photo ingestion pipeline after METADATA_EXTRACTED, and
also directly by POST /api/v1/internal/face/process-photo for manual
re-processing. One entry point: :func:`process_photo_for_faces`.

Correctness rules (each one prevents a concrete class of bug):

  1. **Re-check consent inside the worker.** Revocation can land between
     the moment the photo was queued and the moment the worker runs.
     Reading a cached flag from the caller is not enough — we hit
     ``face_pipeline_active`` here so the revocation is honored.

  2. **workspace_id is sourced from the PhotoAsset row**, never from a
     caller-supplied parameter. A compromised caller cannot trick this
     function into writing one workspace's face data into another.

  3. **Qdrant upsert happens AFTER the PG INSERT flush.** If Qdrant
     rejects the write we delete the in-session PG rows and re-raise.
     The outer pipeline catches the exception and logs it; face
     processing is explicitly non-critical to photo searchability.

  4. **Idempotent.** If face_detections already exist for this photo
     (e.g. a re-run from the manual endpoint), they are wiped from PG
     AND Qdrant before the new batch is inserted, so two calls produce
     one set of rows, not two.

Logging (ART-14 §4, ART-27): counts and ids only. Never bbox coordinates,
never embedding floats, never filenames. The S11-005 whitelist in
test_face_logging.py covers the detection log; this module adds an
analogous ``face_ingestion.*`` family with the same discipline.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.errors import FaceModelInvalidImageError, NotFoundError
from api.services import metrics_service
from api.services.face import crypto
from api.services.face.face_model import FaceModel
from api.services.flags import face_pipeline_active
from api.services.qdrant_client import get_qdrant
from api.services.resource_controller import Priority, acquire_slot

logger = structlog.get_logger()

FACE_EMBEDDINGS_COLLECTION = "face_embeddings"


async def _wipe_existing_detections(
    photo_asset_id: UUID,
    db: AsyncSession,
    qdrant: Any,
) -> int:
    """Delete any prior face_detections for this photo from PG + Qdrant.

    Returns the number of rows removed. Qdrant deletion failures are
    logged but do not raise — Postgres is the system of record.
    """
    existing = (
        (
            await db.execute(
                select(FaceDetection).where(
                    FaceDetection.photo_asset_id == photo_asset_id,
                    FaceDetection.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not existing:
        return 0

    from qdrant_client.models import PointIdsList

    point_ids = [str(row.qdrant_point_id) for row in existing]
    try:
        await qdrant.delete(
            collection_name=FACE_EMBEDDINGS_COLLECTION,
            points_selector=PointIdsList(points=point_ids),
        )
    except Exception:
        logger.warning(
            "face_ingestion_qdrant_cleanup_failed",
            photo_asset_id=str(photo_asset_id),
            exc_info=True,
        )

    for row in existing:
        await db.delete(row)
    await db.flush()
    return len(existing)


async def process_photo_for_faces(
    photo_asset_id: UUID,
    db: AsyncSession,
    *,
    qdrant: Any = None,
    face_model: FaceModel | None = None,
) -> int:
    """Detect, embed, persist faces for one photo. Returns face_count.

    Short-circuits to 0 (no work, no writes) when the face pipeline is
    not active for the photo's workspace — absence of consent, missing
    key, or disabled flag all collapse to "do nothing".

    Args:
        photo_asset_id: Target photo. workspace_id is read from the
            PhotoAsset row (defense in depth), never accepted as an
            argument.
        db: Caller-owned async session. This function flushes but does
            not commit — the caller controls the transaction.
        qdrant: Optional qdrant client override (for tests). Defaults
            to the module singleton.
        face_model: Optional FaceModel override (for tests). Defaults
            to ``FaceModel.instance()``. If not already loaded, a
            single idempotent ``load()`` attempt is made.

    Raises:
        NotFoundError: photo_asset or its File row is missing.
        FaceModelInvalidImageError: the image bytes could not be read
            or decoded.
        Exception: propagated from Qdrant upsert failures after PG
            rollback of the pending rows.
    """
    # 1. Load photo_asset — workspace_id source of truth
    photo = (
        await db.execute(
            select(PhotoAsset).where(PhotoAsset.id == photo_asset_id)
        )
    ).scalar_one_or_none()
    if photo is None:
        raise NotFoundError(
            error_code="PHOTO_ASSET_NOT_FOUND",
            message=f"PhotoAsset {photo_asset_id} not found.",
        )

    workspace_id = photo.workspace_id

    # 2. Re-check consent here, not at queue time. Revocation may have
    #    landed in between — ART-15 §3 forbids any write after revocation.
    if not await face_pipeline_active(workspace_id, db):
        logger.info(
            "face_ingestion_skipped_consent_inactive",
            photo_asset_id=str(photo_asset_id),
            workspace_id=str(workspace_id),
        )
        return 0

    # 3. Resolve clients (injected or module defaults).
    if qdrant is None:
        qdrant = get_qdrant()
    if face_model is None:
        face_model = FaceModel.instance()

    if not face_model.loaded:
        face_model.load()
    if not face_model.loaded:
        logger.warning(
            "face_ingestion_model_unavailable",
            photo_asset_id=str(photo_asset_id),
            load_error=face_model.load_error,
        )
        return 0

    # 4. Resolve the on-disk file via the File row.
    file_row = (
        await db.execute(select(File).where(File.id == photo.file_id))
    ).scalar_one_or_none()
    if file_row is None:
        raise NotFoundError(
            error_code="PHOTO_FILE_NOT_FOUND",
            message=(
                f"File row for photo_asset {photo_asset_id} not found."
            ),
        )

    try:
        image_bytes = await asyncio.to_thread(
            Path(file_row.path).read_bytes
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise FaceModelInvalidImageError(
            error_code="FACE_MODEL_INVALID_IMAGE",
            message=f"Could not read image file: {type(exc).__name__}",
        ) from exc

    # 5. Idempotency wipe (re-runs produce one set of rows, not N).
    wiped = await _wipe_existing_detections(photo_asset_id, db, qdrant)
    if wiped:
        logger.info(
            "face_ingestion_idempotent_wipe",
            photo_asset_id=str(photo_asset_id),
            wiped=wiped,
        )

    # 6. Detect + embed under the background low-priority slot.
    detect_started = time.perf_counter()
    async with acquire_slot(Priority.P4_BACKGROUND_LOW):
        faces = await asyncio.to_thread(
            face_model.detect_and_embed,
            image_bytes,
            photo_asset_id=photo_asset_id,
        )
    detect_latency_ms = (time.perf_counter() - detect_started) * 1000.0
    try:
        await metrics_service.record_face_detection_latency(
            workspace_id, detect_latency_ms
        )
    except Exception:
        logger.debug("face_metric_latency_failed", exc_info=True)

    if not faces:
        photo.face_count = 0
        # S11-007: stamp the backfill horizon even when no faces are
        # found — "we ran detection, outcome was zero" is distinct from
        # "we never ran detection", and backfill must not keep picking
        # this photo up on every run.
        photo.face_processed_at = datetime.now(timezone.utc)
        await db.flush()
        logger.info(
            "face_ingestion_no_faces_found",
            photo_asset_id=str(photo_asset_id),
        )
        return 0

    # 7. Insert PG rows first so they receive their server-side ids,
    #    then build Qdrant points with the face_detection_id populated.
    pending_rows: list[FaceDetection] = []
    for face in faces:
        row = FaceDetection(
            workspace_id=workspace_id,
            photo_asset_id=photo_asset_id,
            bbox_json=face.bbox,
            embedding_encrypted=crypto.encrypt_embedding(face.embedding),
            detector_version=face_model.detector_version,
            recognizer_version=face_model.recognizer_version,
            detection_score=face.detection_score,
            qdrant_point_id=uuid4(),
        )
        db.add(row)
        pending_rows.append(row)
    await db.flush()

    from qdrant_client.models import PointStruct

    points = [
        PointStruct(
            id=str(row.qdrant_point_id),
            vector=list(face.embedding),
            payload={
                # Mandatory workspace isolation control (Golden Rule #1).
                "workspace_id": str(workspace_id),
                "photo_asset_id": str(photo_asset_id),
                "face_detection_id": str(row.id),
                "detector_version": face_model.detector_version,
            },
        )
        for row, face in zip(pending_rows, faces, strict=True)
    ]

    try:
        await qdrant.upsert(
            collection_name=FACE_EMBEDDINGS_COLLECTION,
            points=points,
        )
    except Exception:
        logger.error(
            "face_ingestion_qdrant_upsert_failed",
            photo_asset_id=str(photo_asset_id),
            pending_count=len(pending_rows),
            exc_info=True,
        )
        # Roll back PG rows so we don't orphan them when the caller commits.
        for row in pending_rows:
            await db.delete(row)
        await db.flush()
        raise

    photo.face_count = len(pending_rows)
    photo.face_processed_at = datetime.now(timezone.utc)
    await db.flush()

    # S12-002: incremental cluster assignment per new face. Runs AFTER
    # the Qdrant upsert so the search path sees the rest of the
    # workspace's embeddings (and the must_not filter excludes *this*
    # face so we don't self-match). Fire-and-forget — assignment
    # failures do NOT fail the photo ingestion. A full re-cluster
    # (S12-001) will heal any gaps later.
    from api.services.face.incremental_cluster import assign_face_to_cluster

    for row in pending_rows:
        try:
            await assign_face_to_cluster(row.id, db, qdrant)
        except Exception:
            logger.warning(
                "face_ingestion_cluster_assign_failed",
                face_detection_id=str(row.id),
                exc_info=True,
            )

    # S11-008: emit counters + latency for the hourly/daily flushers.
    # Fire-and-forget — metrics failures never block face processing.
    try:
        await metrics_service.record_face_event(
            workspace_id, "detections_created", value=len(pending_rows)
        )
    except Exception:
        logger.debug("face_metric_emit_failed", exc_info=True)

    logger.info(
        "face_ingestion_complete",
        photo_asset_id=str(photo_asset_id),
        workspace_id=str(workspace_id),
        face_count=len(pending_rows),
    )
    return len(pending_rows)
