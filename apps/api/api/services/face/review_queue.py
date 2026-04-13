"""Review Queue service — surface clusters awaiting user confirmation (S12-005).

The review queue is a read surface over ``face_clusters``. It joins
each unconfirmed, populated cluster with:

  - a sample of up to 6 face_detections (highest detection_score)
  - the photo_assets those detections point at (for thumbnails)
  - the first/last ``taken_at`` across all member photos
  - the cached top candidate from ``candidates_json``
    (populated by the S12-003 scorer)

Confirm/reject actions do NOT live here — they go through the S12-004
people service so there's exactly one audit trail per state change.
The review queue only exposes *reads* plus a per-user "skip" marker.

Design rules:

  1. **Workspace isolation.** Every SELECT scopes on workspace_id.
     The caller is the router, which derives workspace_id from the
     authenticated user.

  2. **Skip is per-user, not per-workspace.** Another workspace
     member can still review clusters someone else has skipped —
     skipping is a UI convenience, not a data-level decision.
     Stored as individual Redis keys with a 24h TTL each, so stale
     skips don't block review forever.

  3. **Candidate scores are the sort key.** Highest-score first means
     the reviewer sees the confidence-worthy clusters before the
     noise. Ties are broken by cluster_id for pagination stability.

  4. **PII-safe logging.** Cluster ids, workspace ids, counts — never
     contact display_name, never embeddings, never image bytes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.photo_asset import PhotoAsset
from api.errors import NotFoundError
from api.schemas.review_queue import (
    ReviewCandidate,
    ReviewQueueDetailResponse,
    ReviewQueueItem,
)
from api.services.face.clustering_service import get_clustering_params
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()


SAMPLE_SIZE = 6
SKIP_TTL_SECS = 24 * 3600
_SKIP_PREFIX = "skipped:"


def _skip_key(user_id: UUID, cluster_id: UUID) -> str:
    return f"{_SKIP_PREFIX}{user_id}:{cluster_id}"


async def _is_skipped(user_id: UUID, cluster_id: UUID) -> bool:
    try:
        r = get_redis(REDIS_DB_CACHE)
        value = await r.get(_skip_key(user_id, cluster_id))
        return value is not None
    except Exception:
        logger.debug("review_skip_check_failed", exc_info=True)
        return False


async def mark_skipped(user_id: UUID, cluster_id: UUID) -> None:
    """Best-effort Redis write. Failures are swallowed — skipping is
    advisory, not load-bearing."""
    try:
        r = get_redis(REDIS_DB_CACHE)
        await r.set(_skip_key(user_id, cluster_id), "1", ex=SKIP_TTL_SECS)
    except Exception:
        logger.debug("review_skip_mark_failed", exc_info=True)


# ── Candidate parsing ──────────────────────────────────────────────────────


def _parse_candidates(
    raw: list[Any] | None,
) -> tuple[ReviewCandidate | None, list[ReviewCandidate]]:
    if not raw:
        return None, []
    parsed: list[ReviewCandidate] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            parsed.append(ReviewCandidate.model_validate(entry))
        except Exception:
            continue
    parsed.sort(key=lambda c: c.score, reverse=True)
    if not parsed:
        return None, []
    return parsed[0], parsed[1:5]


def _confidence_bucket(top: ReviewCandidate | None) -> str:
    if top is None:
        return "none"
    if top.score >= 0.75:
        return "high"
    if top.score >= 0.50:
        return "medium"
    return "low"


# ── Per-cluster enrichment ─────────────────────────────────────────────────


async def _load_sample_members(
    cluster_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    limit: int,
) -> tuple[list[UUID], list[UUID]]:
    """Return (sample_face_detection_ids, sample_photo_asset_ids), ordered
    by detection_score DESC so the UI sees the clearest faces first.
    Both lists have the same length — the i-th face_detection is in the
    i-th photo_asset.
    """
    stmt = (
        select(FaceDetection.id, FaceDetection.photo_asset_id)
        .where(
            and_(
                FaceDetection.cluster_id == cluster_id,
                FaceDetection.workspace_id == workspace_id,
                FaceDetection.deleted_at.is_(None),
            )
        )
        .order_by(desc(FaceDetection.detection_score), FaceDetection.id)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return (
        [r.id for r in rows],
        [r.photo_asset_id for r in rows],
    )


async def _load_all_members(
    cluster_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> tuple[list[UUID], list[UUID]]:
    stmt = (
        select(FaceDetection.id, FaceDetection.photo_asset_id)
        .where(
            and_(
                FaceDetection.cluster_id == cluster_id,
                FaceDetection.workspace_id == workspace_id,
                FaceDetection.deleted_at.is_(None),
            )
        )
        .order_by(desc(FaceDetection.detection_score), FaceDetection.id)
    )
    rows = (await db.execute(stmt)).all()
    return (
        [r.id for r in rows],
        [r.photo_asset_id for r in rows],
    )


async def _load_time_span(
    cluster_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> tuple[datetime | None, datetime | None]:
    stmt = (
        select(
            func.min(PhotoAsset.taken_at).label("first_seen"),
            func.max(PhotoAsset.taken_at).label("last_seen"),
        )
        .join(FaceDetection, FaceDetection.photo_asset_id == PhotoAsset.id)
        .where(
            and_(
                FaceDetection.cluster_id == cluster_id,
                PhotoAsset.workspace_id == workspace_id,
            )
        )
    )
    row = (await db.execute(stmt)).one()
    return row.first_seen, row.last_seen


async def _build_item(
    cluster: FaceCluster,
    db: AsyncSession,
) -> ReviewQueueItem:
    top, others = _parse_candidates(cluster.candidates_json)
    sample_det, sample_photo = await _load_sample_members(
        cluster.id, cluster.workspace_id, db, limit=SAMPLE_SIZE
    )
    first_seen, last_seen = await _load_time_span(
        cluster.id, cluster.workspace_id, db
    )
    return ReviewQueueItem(
        cluster_id=cluster.id,
        member_count=int(cluster.member_count or 0),
        sample_face_detection_ids=sample_det,
        sample_photo_asset_ids=sample_photo,
        top_candidate=top,
        other_candidates=others,
        confidence_bucket=_confidence_bucket(top),
        first_seen_at=first_seen,
        last_seen_at=last_seen,
    )


# ── Public API ─────────────────────────────────────────────────────────────


async def list_pending(
    *,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
    confidence_filter: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[ReviewQueueItem], str | None]:
    """Return the next page of clusters awaiting human review.

    Ordering: top candidate score DESC, then cluster_id for stability.
    The cursor is the stringified cluster_id of the last returned row;
    callers pass it back to fetch the next page.
    """
    params = await get_clustering_params(workspace_id, db)
    stmt = (
        select(FaceCluster)
        .where(
            and_(
                FaceCluster.workspace_id == workspace_id,
                FaceCluster.deleted_at.is_(None),
                FaceCluster.cluster_state == "unconfirmed",
                FaceCluster.trusted_person_id.is_(None),
                FaceCluster.member_count >= params.min_cluster_size,
            )
        )
        .order_by(FaceCluster.id)
    )
    clusters = (await db.execute(stmt)).scalars().all()

    # Build items, skipping per-user-skipped clusters up front so
    # confidence filtering still produces stable pages.
    items: list[ReviewQueueItem] = []
    for cluster in clusters:
        if await _is_skipped(user_id, cluster.id):
            continue
        item = await _build_item(cluster, db)
        if confidence_filter is not None and item.confidence_bucket != confidence_filter:
            continue
        items.append(item)

    def _sort_key(it: ReviewQueueItem) -> tuple[float, str]:
        score = it.top_candidate.score if it.top_candidate else 0.0
        return (-score, str(it.cluster_id))

    items.sort(key=_sort_key)

    start = 0
    if cursor:
        for idx, it in enumerate(items):
            if str(it.cluster_id) == cursor:
                start = idx + 1
                break

    page = items[start : start + limit + 1]
    next_cursor: str | None = None
    if len(page) > limit:
        page = page[:limit]
        next_cursor = str(page[-1].cluster_id)

    logger.info(
        "review_queue_list_pending",
        workspace_id=str(workspace_id),
        user_id=str(user_id),
        returned=len(page),
        total_eligible=len(items),
        confidence_filter=confidence_filter,
    )
    return page, next_cursor


async def get_item(
    *,
    cluster_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> ReviewQueueDetailResponse:
    cluster = (
        await db.execute(
            select(FaceCluster).where(
                and_(
                    FaceCluster.id == cluster_id,
                    FaceCluster.workspace_id == workspace_id,
                    FaceCluster.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if cluster is None:
        raise NotFoundError(
            error_code="CLUSTER_NOT_FOUND",
            message="Face cluster not found.",
        )
    top, others = _parse_candidates(cluster.candidates_json)
    all_det, all_photos = await _load_all_members(cluster_id, workspace_id, db)
    first_seen, last_seen = await _load_time_span(cluster_id, workspace_id, db)
    return ReviewQueueDetailResponse(
        cluster_id=cluster_id,
        member_count=int(cluster.member_count or 0),
        face_detection_ids=all_det,
        photo_asset_ids=all_photos,
        top_candidate=top,
        other_candidates=others,
        confidence_bucket=_confidence_bucket(top),
        first_seen_at=first_seen,
        last_seen_at=last_seen,
    )


async def skip(
    *,
    cluster_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> None:
    """Tag a cluster as skipped for this user (24h TTL).

    Validates that the cluster exists in the caller's workspace so
    users can't blacklist foreign clusters via a tampered id.
    """
    cluster = (
        await db.execute(
            select(FaceCluster.id).where(
                and_(
                    FaceCluster.id == cluster_id,
                    FaceCluster.workspace_id == workspace_id,
                    FaceCluster.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if cluster is None:
        raise NotFoundError(
            error_code="CLUSTER_NOT_FOUND",
            message="Face cluster not found.",
        )
    await mark_skipped(user_id, cluster_id)
    logger.info(
        "review_queue_skipped",
        workspace_id=str(workspace_id),
        user_id=str(user_id),
        cluster_id=str(cluster_id),
    )
