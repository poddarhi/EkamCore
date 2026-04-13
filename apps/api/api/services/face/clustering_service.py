"""HDBSCAN clustering of face embeddings (S12-001).

Groups face_detection rows in a workspace into face_clusters via
HDBSCAN over L2-normalized ArcFace embeddings. Designed for Sprint 12's
People Graph review queue: the clusters it produces are the input to
the review queue, where a human labels them with names.

Design rules (each one prevents a concrete bug class):

  1. **Consent-gated.** `cluster_workspace` re-checks
     `face_pipeline_active(workspace_id)` before doing any work. If
     consent has been revoked since the trigger landed, the function
     raises `FaceConsentRequiredError` and writes nothing.

  2. **Full re-cluster, not incremental.** HDBSCAN is density-based
     and its cluster ids are not stable across runs; a single new
     face can reshape neighboring clusters. We re-cluster everything
     in the workspace on each run. Stability of cluster *identity*
     (so a user who named "cluster 7 = Alice" still sees Alice after
     re-cluster) is preserved by matching new label groups to old
     face_clusters rows by majority member overlap.

  3. **L2-normalized embeddings + euclidean metric.** ArcFace embeds
     are trained for cosine similarity. For unit vectors,
     `euclidean² = 2 * cosine_distance`, so running HDBSCAN with
     `metric="euclidean"` on L2-normalized inputs is equivalent to
     cosine clustering — and avoids the pyfunc-metric slow path.
     The workspace-configurable `cluster_selection_epsilon` is
     documented in *cosine* space; we convert to euclidean space at
     fit time (`sqrt(2 * cosine_eps)`).

  4. **Lazy import of hdbscan.** The heavy dependency is imported
     inside `cluster_workspace` (or injected via `hdbscan_module` for
     tests) so the module stays importable when the package is not
     installed. Pattern mirrors `face_model.py::_ensure_cv2_numpy`.

  5. **PII-safe logging (ART-14 §4).** Counts, ids, durations, and
     versions only. Never bbox coords, never embeddings, never
     centroids in plaintext.

  6. **Workspace isolation.** All queries scope on `workspace_id`.
     Re-clustering workspace A never touches workspace B's rows —
     asserted by `tests/security/test_clustering_isolation.py`.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.setting import Setting
from api.errors import FaceConsentRequiredError, ServiceUnavailableError
from api.services import audit
from api.services.face import crypto
from api.services.flags import face_pipeline_active
from api.services.resource_controller import Priority, acquire_slot

logger = structlog.get_logger()

# numpy is always available (pillow depends on it). hdbscan is lazy.
import numpy as np

_PHOTO_INTEL_NAMESPACE = "photo_intelligence"
_KEY_MIN_CLUSTER_SIZE = "min_cluster_size"
_KEY_CLUSTER_EPSILON = "cluster_selection_epsilon"


# ── Result models ──────────────────────────────────────────────────────────


class ClusteringParams(BaseModel):
    """Per-workspace tunables stored in ``settings`` under the
    photo_intelligence namespace. Defaults from ART-21 §3.5."""

    model_config = ConfigDict(extra="forbid")

    min_cluster_size: int = Field(default=3, ge=2, le=50)
    min_samples: int = Field(default=2, ge=1, le=50)
    cluster_selection_epsilon: float = Field(
        default=0.35, ge=0.0, le=1.0,
        description="Cosine-space distance threshold. Internally converted to euclidean.",
    )
    metric: str = "euclidean"
    cluster_selection_method: str = "leaf"


class ClusterResult(BaseModel):
    """One row in the per-face result set (not currently returned by
    the service but exposed for future inspection APIs)."""

    cluster_id: UUID | None
    face_detection_id: UUID
    confidence: float


class ClusteringReport(BaseModel):
    workspace_id: UUID
    face_count: int
    cluster_count: int
    noise_count: int
    before_cluster_count: int
    reused_cluster_count: int
    new_cluster_count: int
    orphaned_cluster_count: int
    duration_ms: int


# ── Per-workspace params (tiny settings_service analogue) ──────────────────


async def get_clustering_params(
    workspace_id: UUID, db: AsyncSession
) -> ClusteringParams:
    """Read per-workspace clustering params from the settings table.

    Missing row → `ClusteringParams()` defaults. Malformed value → log
    a warning and fall back to the default for that field only.
    """
    row = (
        await db.execute(
            select(Setting).where(
                and_(
                    Setting.workspace_id == workspace_id,
                    Setting.user_id.is_(None),
                    Setting.namespace == _PHOTO_INTEL_NAMESPACE,
                    Setting.key.in_([_KEY_MIN_CLUSTER_SIZE, _KEY_CLUSTER_EPSILON]),
                )
            )
        )
    ).scalars().all()

    kwargs: dict[str, Any] = {}
    for r in row:
        try:
            if r.key == _KEY_MIN_CLUSTER_SIZE:
                kwargs["min_cluster_size"] = int(r.value_json["value"])
            elif r.key == _KEY_CLUSTER_EPSILON:
                kwargs["cluster_selection_epsilon"] = float(
                    r.value_json["value"]
                )
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "clustering_params_parse_failed",
                workspace_id=str(workspace_id),
                key=r.key,
            )
    return ClusteringParams(**kwargs)


async def set_clustering_params(
    workspace_id: UUID, params: ClusteringParams, db: AsyncSession
) -> None:
    """Upsert the two workspace-scoped clustering settings rows."""
    for key, value in (
        (_KEY_MIN_CLUSTER_SIZE, params.min_cluster_size),
        (_KEY_CLUSTER_EPSILON, params.cluster_selection_epsilon),
    ):
        existing = (
            await db.execute(
                select(Setting).where(
                    and_(
                        Setting.workspace_id == workspace_id,
                        Setting.user_id.is_(None),
                        Setting.namespace == _PHOTO_INTEL_NAMESPACE,
                        Setting.key == key,
                    )
                )
            )
        ).scalar_one_or_none()
        payload = {"value": value}
        if existing is None:
            db.add(
                Setting(
                    workspace_id=workspace_id,
                    user_id=None,
                    namespace=_PHOTO_INTEL_NAMESPACE,
                    key=key,
                    value_json=payload,
                )
            )
        else:
            existing.value_json = payload
    await db.flush()


# ── Lazy hdbscan import ────────────────────────────────────────────────────

_hdbscan: Any = None


def _ensure_hdbscan() -> Any:
    global _hdbscan
    if _hdbscan is not None:
        return _hdbscan
    try:
        import hdbscan as real_hdbscan  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise ServiceUnavailableError(
            error_code="FACE_CLUSTERING_LIB_UNAVAILABLE",
            message=(
                f"hdbscan import failed: {type(exc).__name__}: {exc}. "
                "Run `cd apps/api && poetry install` to pull the library."
            ),
        ) from exc
    _hdbscan = real_hdbscan
    return _hdbscan


# ── Core service entry point ───────────────────────────────────────────────


async def cluster_workspace(
    workspace_id: UUID,
    db: AsyncSession,
    *,
    params: ClusteringParams | None = None,
    hdbscan_module: Any = None,
) -> ClusteringReport:
    """Full re-cluster of a workspace's face_detections.

    Steps:
      1. Consent re-check (face_pipeline_active).
      2. Acquire P3_BACKGROUND_IMPORTANT slot.
      3. Load every FaceDetection in the workspace with its encrypted
         embedding.
      4. Decrypt + L2-normalize → N×512 float32 array.
      5. Run HDBSCAN; -1 labels are noise.
      6. Group new labels and match each to an existing cluster by
         majority member overlap. Unmatched labels → new face_clusters
         rows; unmatched old clusters → soft-deleted with
         cluster_state='merged'.
      7. Bulk update face_detections.cluster_id (clear all first,
         then assign).
      8. Recompute + encrypt each cluster's centroid (mean of L2-
         normalized members, re-normalized).
      9. audit_log `face_clusters_recomputed`.

    Returns a ClusteringReport. The caller owns the transaction and
    is responsible for commit/rollback.
    """
    started = time.perf_counter()

    # Step 1 — consent re-check
    if not await face_pipeline_active(workspace_id, db):
        raise FaceConsentRequiredError(
            error_code="FACE_CONSENT_REQUIRED",
            message=(
                "Face clustering requires active consent for this workspace."
            ),
        )

    if params is None:
        params = await get_clustering_params(workspace_id, db)

    # Step 2 — P3 slot (background important; yields to P1 query / P2 pack)
    async with acquire_slot(Priority.P3_BACKGROUND_IMPORTANT):
        return await _do_cluster(
            workspace_id=workspace_id,
            db=db,
            params=params,
            hdbscan_module=hdbscan_module,
            started=started,
        )


async def _do_cluster(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    params: ClusteringParams,
    hdbscan_module: Any,
    started: float,
) -> ClusteringReport:
    # ── Load detections ────────────────────────────────────────────
    detections = (
        (
            await db.execute(
                select(FaceDetection)
                .where(
                    and_(
                        FaceDetection.workspace_id == workspace_id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
                .order_by(FaceDetection.id)
            )
        )
        .scalars()
        .all()
    )

    # Existing clusters (before this run) + their member sets, used
    # for the identity-stability match pass.
    existing_clusters = (
        (
            await db.execute(
                select(FaceCluster).where(
                    and_(
                        FaceCluster.workspace_id == workspace_id,
                        FaceCluster.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    before_cluster_count = len(existing_clusters)

    old_member_map: dict[UUID, set[UUID]] = {}
    for cl in existing_clusters:
        member_ids = (
            await db.execute(
                select(FaceDetection.id).where(
                    and_(
                        FaceDetection.cluster_id == cl.id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        ).scalars().all()
        old_member_map[cl.id] = set(member_ids)

    # Empty workspace fast path — still emit audit so timelines are
    # complete.
    if not detections:
        await _emit_audit(
            db=db,
            workspace_id=workspace_id,
            face_count=0,
            cluster_count=0,
            noise_count=0,
            before_cluster_count=before_cluster_count,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return ClusteringReport(
            workspace_id=workspace_id,
            face_count=0,
            cluster_count=0,
            noise_count=0,
            before_cluster_count=before_cluster_count,
            reused_cluster_count=0,
            new_cluster_count=0,
            orphaned_cluster_count=before_cluster_count,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # ── Decrypt + L2-normalize ─────────────────────────────────────
    ids: list[UUID] = []
    vectors: list[list[float]] = []
    decrypt_failures = 0
    for det in detections:
        try:
            vec = crypto.decrypt_embedding(det.embedding_encrypted)
        except Exception:
            decrypt_failures += 1
            logger.warning(
                "clustering_decrypt_failed",
                workspace_id=str(workspace_id),
                face_detection_id=str(det.id),
            )
            continue
        if len(vec) != det.embedding_dim:
            decrypt_failures += 1
            continue
        ids.append(det.id)
        vectors.append(vec)

    if not vectors:
        # Every row failed to decrypt. Emit audit, return noise-only.
        duration_ms = int((time.perf_counter() - started) * 1000)
        await _emit_audit(
            db=db,
            workspace_id=workspace_id,
            face_count=len(detections),
            cluster_count=0,
            noise_count=len(detections),
            before_cluster_count=before_cluster_count,
            duration_ms=duration_ms,
            decrypt_failures=decrypt_failures,
        )
        return ClusteringReport(
            workspace_id=workspace_id,
            face_count=len(detections),
            cluster_count=0,
            noise_count=len(detections),
            before_cluster_count=before_cluster_count,
            reused_cluster_count=0,
            new_cluster_count=0,
            orphaned_cluster_count=before_cluster_count,
            duration_ms=duration_ms,
        )

    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    arr = arr / norms

    # ── Run HDBSCAN ────────────────────────────────────────────────
    hb = hdbscan_module or _ensure_hdbscan()

    # Convert the workspace-facing cosine epsilon to euclidean space
    # for HDBSCAN's euclidean metric on unit vectors.
    eps_euclidean = math.sqrt(max(2.0 * params.cluster_selection_epsilon, 0.0))

    try:
        clusterer = hb.HDBSCAN(
            min_cluster_size=params.min_cluster_size,
            min_samples=params.min_samples,
            cluster_selection_epsilon=eps_euclidean,
            metric=params.metric,
            cluster_selection_method=params.cluster_selection_method,
        )
        clusterer.fit(arr)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "clustering_fit_failed",
            workspace_id=str(workspace_id),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise ServiceUnavailableError(
            error_code="FACE_CLUSTERING_FAILED",
            message=f"HDBSCAN fit failed: {type(exc).__name__}",
        ) from exc

    labels = np.asarray(clusterer.labels_)
    probabilities = np.asarray(
        getattr(clusterer, "probabilities_", np.ones(len(labels)))
    )

    # ── Group new labels ───────────────────────────────────────────
    label_to_det_ids: dict[int, list[UUID]] = defaultdict(list)
    label_to_embeddings: dict[int, list[np.ndarray]] = defaultdict(list)
    label_to_probs: dict[int, list[float]] = defaultdict(list)
    noise_count = 0
    for idx, (det_id, label) in enumerate(zip(ids, labels, strict=True)):
        label_int = int(label)
        if label_int < 0:
            noise_count += 1
            continue
        label_to_det_ids[label_int].append(det_id)
        label_to_embeddings[label_int].append(arr[idx])
        label_to_probs[label_int].append(float(probabilities[idx]))

    # ── Match new labels to existing clusters by majority overlap ──
    # For each new label, find the old cluster whose member set
    # overlaps most with this label's new members. Only reuse if the
    # overlap is at least half of the old cluster's members (so a tiny
    # spurious match can't hijack an old cluster's name).
    label_to_cluster_id: dict[int, UUID] = {}
    used_old_ids: set[UUID] = set()
    new_rows_by_label: dict[int, FaceCluster] = {}

    for label, det_ids in label_to_det_ids.items():
        det_id_set = set(det_ids)
        best_old: UUID | None = None
        best_overlap = 0
        for old_id, old_members in old_member_map.items():
            if old_id in used_old_ids or not old_members:
                continue
            overlap = len(det_id_set & old_members)
            if overlap > best_overlap and overlap * 2 >= len(old_members):
                best_overlap = overlap
                best_old = old_id
        if best_old is not None:
            label_to_cluster_id[label] = best_old
            used_old_ids.add(best_old)
        else:
            new_row = FaceCluster(
                workspace_id=workspace_id,
                member_count=0,
                cluster_state="unconfirmed",
            )
            db.add(new_row)
            new_rows_by_label[label] = new_row

    await db.flush()  # populate ids on the freshly-added cluster rows
    for label, row in new_rows_by_label.items():
        label_to_cluster_id[label] = row.id

    # ── Bulk-update face_detections.cluster_id ─────────────────────
    # Clear the whole workspace first so a detection that moved to
    # noise this run loses its stale cluster_id.
    await db.execute(
        update(FaceDetection)
        .where(
            and_(
                FaceDetection.workspace_id == workspace_id,
                FaceDetection.deleted_at.is_(None),
            )
        )
        .values(cluster_id=None)
    )
    for label, det_ids in label_to_det_ids.items():
        cid = label_to_cluster_id[label]
        await db.execute(
            update(FaceDetection)
            .where(FaceDetection.id.in_(det_ids))
            .values(cluster_id=cid)
        )

    # ── Recompute centroids and persist encrypted ──────────────────
    for label, embs in label_to_embeddings.items():
        stacked = np.stack(embs)
        centroid = stacked.mean(axis=0)
        n = float(np.linalg.norm(centroid))
        if n > 0:
            centroid = centroid / n
        cid = label_to_cluster_id[label]
        centroid_ciphertext = crypto.encrypt_embedding(centroid.tolist())
        await db.execute(
            update(FaceCluster)
            .where(FaceCluster.id == cid)
            .values(
                centroid_encrypted=centroid_ciphertext,
                member_count=len(embs),
            )
        )

    # ── Orphan the unused old clusters ─────────────────────────────
    orphan_old_ids = set(old_member_map.keys()) - used_old_ids
    now = datetime.now(timezone.utc)
    orphan_count = 0
    for orphan_id in orphan_old_ids:
        await db.execute(
            update(FaceCluster)
            .where(FaceCluster.id == orphan_id)
            .values(
                cluster_state="merged",
                deleted_at=now,
                member_count=0,
            )
        )
        orphan_count += 1

    await db.flush()

    duration_ms = int((time.perf_counter() - started) * 1000)
    cluster_count = len(label_to_cluster_id)
    await _emit_audit(
        db=db,
        workspace_id=workspace_id,
        face_count=len(ids),
        cluster_count=cluster_count,
        noise_count=noise_count,
        before_cluster_count=before_cluster_count,
        duration_ms=duration_ms,
        decrypt_failures=decrypt_failures,
    )

    logger.info(
        "face_clustering_complete",
        workspace_id=str(workspace_id),
        face_count=len(ids),
        cluster_count=cluster_count,
        noise_count=noise_count,
        before_count=before_cluster_count,
        reused_count=len(used_old_ids),
        new_count=len(new_rows_by_label),
        orphaned_count=orphan_count,
        duration_ms=duration_ms,
    )

    return ClusteringReport(
        workspace_id=workspace_id,
        face_count=len(ids),
        cluster_count=cluster_count,
        noise_count=noise_count,
        before_cluster_count=before_cluster_count,
        reused_cluster_count=len(used_old_ids),
        new_cluster_count=len(new_rows_by_label),
        orphaned_cluster_count=orphan_count,
        duration_ms=duration_ms,
    )


async def _emit_audit(
    *,
    db: AsyncSession,
    workspace_id: UUID,
    face_count: int,
    cluster_count: int,
    noise_count: int,
    before_cluster_count: int,
    duration_ms: int,
    decrypt_failures: int = 0,
) -> None:
    await audit.log_event(
        db=db,
        action="face_clusters_recomputed",
        object_type="face_clusters",
        workspace_id=workspace_id,
        metadata={
            "before_count": before_cluster_count,
            "after_count": cluster_count,
            "noise_count": noise_count,
            "face_count": face_count,
            "decrypt_failures": decrypt_failures,
            "duration_ms": duration_ms,
        },
    )
