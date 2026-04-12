"""Synchronous, transactional hard-delete of face pipeline data (S11-003).

Replaces the S11-002 stub. Called by ConsentService.revoke() inside the
caller's PG transaction; any exception rolls back the revocation.

Design: ORDER AND FAILURE MODES
────────────────────────────────────────────────────────────────────────────
The deletion order is intentional and legally significant. ART-15 §3 gives
the user a right to erasure of biometric data. Under this contract:

  - UNDER-deletion (biometric data still exists after revoke)     → ILLEGAL
  - OVER-deletion (biometric data gone + some metadata orphaned)  → LEGAL

We therefore delete Qdrant FIRST, because Qdrant stores the encrypted
embeddings — the irreplaceable biometric ciphertext. Once Qdrant is empty
for the workspace, no biometric identifier exists anywhere, no matter
what happens to the PG metadata rows.

The steps, in order:

  1. SELECT streaming of face_detection.id and face_detection.qdrant_point_id
     for this workspace. Used only for the DeleteReport counts — the
     Qdrant delete uses a filter, not an ID list.

  2. Qdrant delete-by-filter on {workspace_id = :ws} against face_embeddings.
     This removes EVERY point tagged with the workspace, including any
     orphans not in face_detections (belt-and-braces).

  3. Qdrant verification: count points with the same filter. Must equal 0.
     If non-zero → raise; caller rolls back; consent stays active.

  4. PG: DELETE FROM face_detections WHERE workspace_id = :ws

  5. PG: DELETE FROM face_clusters   WHERE workspace_id = :ws

  6. PG: UPDATE photo_assets SET face_count = 0 WHERE workspace_id = :ws

  7. PG: INSERT audit_log row action='face_data_hard_deleted' with counts
     and duration. Inside the same transaction — commits together with
     the DELETEs when the caller commits.

  8. Return DeleteReport.

Failure modes:

  Step 2 or 3 fails before any PG deletion: Qdrant may be partially
  emptied (over-deletion is legal); PG intact; caller rolls back;
  consent stays active. Next revoke retry succeeds.

  Steps 4-6 fail after Qdrant empty: Qdrant deletion persisted
  (over-deletion is legal); PG transaction rolls back; caller does NOT
  commit the consent revocation; face pipeline stays "active" at the
  flag level but Qdrant is empty. Retry of revoke is safe — Qdrant
  delete-by-filter is idempotent (already-empty is the expected state).

  Step 7 fails: same as 4-6. Rollback restores the pre-delete PG state.
  Audit row not written; external monitoring can alert on this.

The caller (ConsentService.revoke) MUST call this function BEFORE
tombstoning the consent record so that a failure here is visible in
the caller's rollback cascade.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.photo_asset import PhotoAsset
from api.errors import ServiceUnavailableError
from api.services import audit
from api.services.qdrant_client import get_qdrant

logger = structlog.get_logger()

_FACE_COLLECTION = "face_embeddings"


@dataclass
class DeleteReport:
    """Summary of a hard-delete operation. Returned to the caller and
    recorded in the audit row."""

    detection_count: int
    cluster_count: int
    qdrant_point_count: int
    duration_ms: int


def _workspace_filter(workspace_id: UUID) -> Filter:
    """Build the mandatory workspace_id filter for Qdrant."""
    return Filter(
        must=[
            FieldCondition(
                key="workspace_id",
                match=MatchValue(value=str(workspace_id)),
            )
        ]
    )


async def delete_all_face_data(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    qdrant: AsyncQdrantClient | None = None,
) -> DeleteReport:
    """Synchronously hard-delete all biometric data for a workspace.

    Runs inside the caller's SQLAlchemy transaction. On any failure,
    raises — the caller MUST roll back so that the consent revocation
    that triggered this call also rolls back.

    Args:
        workspace_id: The workspace whose face data is to be erased.
        db: Caller's AsyncSession (used for all PG operations).
        qdrant: Optional Qdrant client. Defaults to the module singleton.
            Tests inject mocks here.

    Returns:
        DeleteReport with counts and duration.

    Raises:
        ServiceUnavailableError with error_code starting in
        FACE_HARD_DELETE_ on any failure. The message is safe to log
        but never leaks workspace-specific data beyond the ID.
    """
    started = time.perf_counter()
    client = qdrant if qdrant is not None else get_qdrant()
    q_filter = _workspace_filter(workspace_id)

    # ── Step 1 ── pre-count for the report
    try:
        detection_count_before = (
            await db.execute(
                select(func.count(FaceDetection.id)).where(
                    FaceDetection.workspace_id == workspace_id
                )
            )
        ).scalar_one()
        cluster_count_before = (
            await db.execute(
                select(func.count(FaceCluster.id)).where(
                    FaceCluster.workspace_id == workspace_id
                )
            )
        ).scalar_one()
    except Exception as exc:
        logger.warning(
            "face_hard_delete_precount_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_PRECOUNT_FAILED",
            message="Could not read face data counts prior to deletion.",
        ) from exc

    # ── Step 2 ── Qdrant delete-by-filter (FIRST: irreplaceable ciphertext)
    try:
        await client.delete(
            collection_name=_FACE_COLLECTION,
            points_selector=FilterSelector(filter=q_filter),
            wait=True,
        )
    except Exception as exc:
        logger.warning(
            "face_hard_delete_qdrant_delete_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_QDRANT_FAILED",
            message="Qdrant delete-by-filter failed. Revocation rolled back.",
        ) from exc

    # ── Step 3 ── Verify Qdrant is empty for this workspace
    try:
        count_result = await client.count(
            collection_name=_FACE_COLLECTION,
            count_filter=q_filter,
            exact=True,
        )
        remaining = int(count_result.count)
    except Exception as exc:
        logger.warning(
            "face_hard_delete_qdrant_verify_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_QDRANT_VERIFY_FAILED",
            message="Qdrant post-delete count failed. Revocation rolled back.",
        ) from exc

    if remaining != 0:
        logger.error(
            "face_hard_delete_qdrant_residue",
            workspace_id=str(workspace_id),
            remaining=remaining,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_QDRANT_RESIDUE",
            message=(
                f"Qdrant still reports {remaining} face embedding points "
                "after delete-by-filter. Revocation rolled back."
            ),
        )

    # ── Step 4 ── PG DELETE face_detections
    try:
        result = await db.execute(
            delete(FaceDetection).where(FaceDetection.workspace_id == workspace_id)
        )
        detection_rows_deleted = result.rowcount or 0
    except Exception as exc:
        logger.warning(
            "face_hard_delete_pg_detections_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_PG_DETECTIONS_FAILED",
            message="PG delete of face_detections failed. Revocation rolled back.",
        ) from exc

    # ── Step 5 ── PG DELETE face_clusters
    try:
        result = await db.execute(
            delete(FaceCluster).where(FaceCluster.workspace_id == workspace_id)
        )
        cluster_rows_deleted = result.rowcount or 0
    except Exception as exc:
        logger.warning(
            "face_hard_delete_pg_clusters_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_PG_CLUSTERS_FAILED",
            message="PG delete of face_clusters failed. Revocation rolled back.",
        ) from exc

    # ── Step 6 ── Zero photo_asset.face_count AND clear face_processed_at.
    # S11-007: clearing face_processed_at resets the backfill horizon so
    # that if consent is granted again later, the backfill service can
    # rediscover these photos and re-process them cleanly.
    try:
        await db.execute(
            update(PhotoAsset)
            .where(PhotoAsset.workspace_id == workspace_id)
            .values(face_count=0, face_processed_at=None)
        )
    except Exception as exc:
        logger.warning(
            "face_hard_delete_pg_photo_count_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_PG_PHOTO_COUNT_FAILED",
            message="PG update of photo_asset.face_count failed. Revocation rolled back.",
        ) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)

    # ── Step 7 ── Audit row (same transaction)
    try:
        await audit.log_event(
            db=db,
            action="face_data_hard_deleted",
            object_type="face_consent",
            workspace_id=workspace_id,
            metadata={
                "detection_count": detection_rows_deleted,
                "cluster_count": cluster_rows_deleted,
                "qdrant_point_count_before_verify": 0,  # Qdrant was verified empty
                "detection_count_before": int(detection_count_before),
                "cluster_count_before": int(cluster_count_before),
                "duration_ms": duration_ms,
            },
        )
    except Exception as exc:
        logger.warning(
            "face_hard_delete_audit_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_HARD_DELETE_AUDIT_FAILED",
            message="Audit row write failed after successful deletion. Revocation rolled back.",
        ) from exc

    logger.info(
        "face_hard_delete_complete",
        workspace_id=str(workspace_id),
        detection_count=detection_rows_deleted,
        cluster_count=cluster_rows_deleted,
        duration_ms=duration_ms,
    )

    return DeleteReport(
        detection_count=detection_rows_deleted,
        cluster_count=cluster_rows_deleted,
        qdrant_point_count=int(detection_count_before),
        duration_ms=duration_ms,
    )
