"""Incremental cluster assignment for online face ingestion (S12-002).

Runs per-face *after* ``process_photo_for_faces`` has written the
face_detection row and upserted its embedding into Qdrant. Decides
whether the new face joins an existing cluster, starts a new one, or
stays unclustered.

This is the "online" counterpart to S12-001's full ``cluster_workspace``
re-cluster. Both must coexist:

  - Incremental assignment keeps the per-photo ingestion experience
    fast and gives the user "this face belongs to {Person}" hints
    without running the full HDBSCAN pass on every photo.

  - Full re-cluster is still the source of truth. Incremental
    assignment is deliberately *conservative* — it refuses to modify
    a confirmed cluster's centroid by more than 0.05 cosine distance
    in one step, leaves borderline faces unclustered, and increments
    a Redis "recluster hint" counter so the manager can surface
    "50+ unclustered faces — consider running a full re-cluster".

Decision tree (single face in, one of three outcomes):

    ┌─ top Qdrant neighbor sim ≥ 0.70
    │   └─ best candidate cluster sim ≥ 0.60
    │       └─ proposed centroid drift ≤ 0.05 for *confirmed* clusters
    │           → MATCH: assign, running-mean centroid update
    │
    ├─ top neighbor sim ≥ 0.55      → WEAK: leave unclustered, hint++
    │
    └─ otherwise                     → NEW: mint unconfirmed cluster, hint++

PII-safe logging (ART-14 §4): log the face_detection_id, workspace_id,
decision name, and similarity *bucket* (very_low / low / medium / high
/ very_high) — never the raw similarity value, never the embedding,
never the centroid. The bucket is coarse enough that it cannot be
used to reconstruct the underlying floats even across many log lines.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import numpy as np
import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.errors import NotFoundError
from api.services.face import crypto
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

FACE_EMBEDDINGS_COLLECTION = "face_embeddings"

# Thresholds (ART-11 online clustering section). Tunable but not
# per-workspace — if a user wants different thresholds the right
# answer is a full re-cluster with adjusted ClusteringParams, not
# per-face knob tuning.
STRONG_NEIGHBOR_SIM: float = 0.70
STRONG_CLUSTER_SIM: float = 0.60
WEAK_NEIGHBOR_SIM: float = 0.55
MAX_CENTROID_DRIFT_COSINE: float = 0.05
TOP_K_NEIGHBORS: int = 5

_RECLUSTER_HINT_PREFIX = "recluster_hint:"
_RECLUSTER_HINT_TTL_SECS = 7 * 86400  # 7 days


# ── Helpers ────────────────────────────────────────────────────────────────


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n <= 0:
        return v
    return v / n


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Both arrays assumed L2-normalized."""
    return float(np.dot(a, b))


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return 1.0 - _cosine_sim(a, b)


def _bucket_similarity(sim: float) -> str:
    """Bucket a similarity score so we can log the *level* without
    leaking the raw float. See the module docstring for why raw
    similarity is considered PII-adjacent."""
    if sim >= 0.90:
        return "very_high"
    if sim >= 0.70:
        return "high"
    if sim >= 0.55:
        return "medium"
    if sim >= 0.30:
        return "low"
    return "very_low"


async def _increment_recluster_hint(workspace_id: UUID) -> None:
    """Best-effort Redis counter bump. Failures are swallowed —
    the hint is an advisory signal, not a correctness gate."""
    try:
        r = get_redis(REDIS_DB_CACHE)
        key = f"{_RECLUSTER_HINT_PREFIX}{workspace_id}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _RECLUSTER_HINT_TTL_SECS)
        await pipe.execute()
    except Exception:
        logger.debug("recluster_hint_incr_failed", exc_info=True)


async def get_recluster_hint_count(workspace_id: UUID) -> int:
    """Read the current hint counter (for admin dashboard, Sprint 13)."""
    try:
        r = get_redis(REDIS_DB_CACHE)
        value = await r.get(f"{_RECLUSTER_HINT_PREFIX}{workspace_id}")
        return int(value) if value is not None else 0
    except Exception:
        logger.debug("recluster_hint_read_failed", exc_info=True)
        return 0


# ── Core: assign a single face ─────────────────────────────────────────────


async def assign_face_to_cluster(
    face_detection_id: UUID,
    db: AsyncSession,
    qdrant: Any,
) -> UUID | None:
    """Assign one face_detection to a cluster.

    Returns the chosen ``cluster_id``, or ``None`` when the face is
    left unclustered (weak match or drift-rejected). Never raises on
    normal decision-tree paths — the caller is expected to call this
    fire-and-forget inside the non-critical face ingestion tail.

    Args:
        face_detection_id: Primary key of the FaceDetection row to
            place. The row must already be flushed (so it has an id)
            and its embedding must already be upserted into Qdrant.
        db: Caller-owned session. This function flushes but does not
            commit.
        qdrant: Async Qdrant client (or a test double). Must support
            ``search(collection_name, query_vector, query_filter,
            limit, with_payload)``.
    """
    # 1. Load the row
    face = (
        await db.execute(
            select(FaceDetection).where(FaceDetection.id == face_detection_id)
        )
    ).scalar_one_or_none()
    if face is None:
        raise NotFoundError(
            error_code="FACE_DETECTION_NOT_FOUND",
            message=f"FaceDetection {face_detection_id} not found.",
        )
    workspace_id = face.workspace_id

    # 2. Decrypt + L2-normalize
    try:
        vec = crypto.decrypt_embedding(face.embedding_encrypted)
    except Exception:
        logger.warning(
            "incremental_decrypt_failed",
            face_detection_id=str(face_detection_id),
        )
        return None
    arr = _l2_normalize(np.asarray(vec, dtype=np.float32))

    # 3. Query Qdrant for top-K neighbors in this workspace, excluding
    #    the face we just inserted (self-match would dominate the
    #    ranking with score 1.0 and derail the decision tree).
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        MatchValue,
    )

    q_filter = Filter(
        must=[
            FieldCondition(
                key="workspace_id",
                match=MatchValue(value=str(workspace_id)),
            )
        ],
        must_not=[
            FieldCondition(
                key="face_detection_id",
                match=MatchValue(value=str(face_detection_id)),
            )
        ],
    )

    try:
        hits = await qdrant.search(
            collection_name=FACE_EMBEDDINGS_COLLECTION,
            query_vector=arr.tolist(),
            query_filter=q_filter,
            limit=TOP_K_NEIGHBORS,
            with_payload=True,
        )
    except Exception:
        logger.warning(
            "incremental_qdrant_search_failed",
            face_detection_id=str(face_detection_id),
            exc_info=True,
        )
        return None

    # 4. No neighbors → this is the very first face (or the only one
    #    after a hard-delete) → mint a brand new cluster.
    if not hits:
        new_id = await _create_new_cluster(
            db, workspace_id, face_detection_id, arr
        )
        await _increment_recluster_hint(workspace_id)
        logger.info(
            "incremental_cluster_assigned",
            workspace_id=str(workspace_id),
            face_detection_id=str(face_detection_id),
            decision="new",
            top_sim_bucket="very_low",
            cluster_sim_bucket="very_low",
            cluster_id=str(new_id),
        )
        return new_id

    top_sim = float(hits[0].score)

    # 5. Collect candidate clusters via neighbor face_detections that
    #    already have cluster_ids assigned.
    neighbor_det_ids: list[UUID] = []
    for h in hits:
        payload = getattr(h, "payload", None) or {}
        raw = payload.get("face_detection_id")
        if not raw:
            continue
        try:
            neighbor_det_ids.append(UUID(str(raw)))
        except (ValueError, TypeError):
            continue

    candidate_clusters: dict[UUID, FaceCluster] = {}
    if neighbor_det_ids:
        neighbors = (
            (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.id.in_(neighbor_det_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        cluster_ids = {
            n.cluster_id for n in neighbors if n.cluster_id is not None
        }
        if cluster_ids:
            clusters = (
                (
                    await db.execute(
                        select(FaceCluster).where(
                            and_(
                                FaceCluster.id.in_(cluster_ids),
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            candidate_clusters = {c.id: c for c in clusters}

    # 6. Score each candidate cluster by cosine similarity of its
    #    decrypted centroid against this face. Keep the best.
    best_cluster_id: UUID | None = None
    best_cluster_sim: float = -1.0
    best_centroid: np.ndarray | None = None
    for cid, cluster in candidate_clusters.items():
        if cluster.centroid_encrypted is None:
            continue
        try:
            centroid_vec = crypto.decrypt_embedding(cluster.centroid_encrypted)
        except Exception:
            continue
        centroid = _l2_normalize(
            np.asarray(centroid_vec, dtype=np.float32)
        )
        sim = _cosine_sim(arr, centroid)
        if sim > best_cluster_sim:
            best_cluster_sim = sim
            best_cluster_id = cid
            best_centroid = centroid

    # 7. Decision tree
    decision = "new"
    chosen_cluster_id: UUID | None = None

    if (
        top_sim >= STRONG_NEIGHBOR_SIM
        and best_cluster_sim >= STRONG_CLUSTER_SIM
        and best_cluster_id is not None
        and best_centroid is not None
    ):
        cluster = candidate_clusters[best_cluster_id]
        old_member_count = max(int(cluster.member_count or 0), 1)
        new_centroid = _l2_normalize(
            (best_centroid * old_member_count + arr)
            / (old_member_count + 1)
        )
        drift = _cosine_distance(best_centroid, new_centroid)

        if (
            cluster.cluster_state == "confirmed"
            and drift > MAX_CENTROID_DRIFT_COSINE
        ):
            # Drift guard: confirmed-cluster centroids may not be
            # shifted by more than 5% cosine distance in a single
            # online step. Leave the face unclustered.
            decision = "drift_rejected"
        else:
            # Assign the face, update the cluster running mean.
            await db.execute(
                update(FaceDetection)
                .where(FaceDetection.id == face_detection_id)
                .values(cluster_id=best_cluster_id)
            )
            new_member_count = old_member_count + 1
            await db.execute(
                update(FaceCluster)
                .where(FaceCluster.id == best_cluster_id)
                .values(
                    centroid_encrypted=crypto.encrypt_embedding(
                        new_centroid.tolist()
                    ),
                    member_count=new_member_count,
                )
            )
            await db.flush()
            chosen_cluster_id = best_cluster_id
            decision = "matched"
            # S12-003: once a cluster crosses the scoring floor
            # (member_count >= 3) tag it for the next batch scoring
            # pass. Best-effort Redis write — failures are ignored.
            if old_member_count < 3 <= new_member_count:
                from api.services.face.candidate_scorer import (
                    mark_cluster_needs_scoring,
                )
                await mark_cluster_needs_scoring(best_cluster_id)

    elif top_sim >= WEAK_NEIGHBOR_SIM:
        decision = "weak"

    else:
        decision = "new"

    # 8. Apply the non-match decisions
    if decision in ("weak", "drift_rejected"):
        # Explicitly ensure cluster_id is NULL — defensive write in
        # case a stale value was present.
        await db.execute(
            update(FaceDetection)
            .where(FaceDetection.id == face_detection_id)
            .values(cluster_id=None)
        )
        await db.flush()
        await _increment_recluster_hint(workspace_id)
        chosen_cluster_id = None
    elif decision == "new":
        chosen_cluster_id = await _create_new_cluster(
            db, workspace_id, face_detection_id, arr
        )
        await _increment_recluster_hint(workspace_id)

    # 9. PII-safe structured log with bucketed similarity
    logger.info(
        "incremental_cluster_assigned",
        workspace_id=str(workspace_id),
        face_detection_id=str(face_detection_id),
        decision=decision,
        top_sim_bucket=_bucket_similarity(top_sim),
        cluster_sim_bucket=_bucket_similarity(best_cluster_sim),
        cluster_id=(
            str(chosen_cluster_id) if chosen_cluster_id is not None else None
        ),
    )
    return chosen_cluster_id


async def _create_new_cluster(
    db: AsyncSession,
    workspace_id: UUID,
    face_detection_id: UUID,
    normalized_embedding: np.ndarray,
) -> UUID:
    """Mint a new unconfirmed face_clusters row seeded with this
    single face and bind the face_detection to it. Returns the new
    cluster id."""
    new_row = FaceCluster(
        workspace_id=workspace_id,
        centroid_encrypted=crypto.encrypt_embedding(
            normalized_embedding.tolist()
        ),
        member_count=1,
        cluster_state="unconfirmed",
    )
    db.add(new_row)
    await db.flush()
    await db.execute(
        update(FaceDetection)
        .where(FaceDetection.id == face_detection_id)
        .values(cluster_id=new_row.id)
    )
    await db.flush()
    return new_row.id
