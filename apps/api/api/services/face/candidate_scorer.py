"""Cluster → contact candidate scoring (S12-003 / ART-11).

Given a face_cluster (grouping of face_detection rows that HDBSCAN or
the incremental assigner thinks belong to the same person), rank the
workspace's contacts by how likely each one *is* that person. The top
candidates are cached on ``face_clusters.candidates_json`` and shown
to the user in the Sprint 13 People Graph review queue.

Design rules (each prevents a concrete bug class):

  1. **Consent-gated.** ``score_workspace_clusters`` re-checks
     ``face_pipeline_active(workspace_id)``. If consent was revoked
     between the trigger and execution we raise
     ``FaceConsentRequiredError`` and write nothing.

  2. **Workspace isolation.** Every SELECT scopes on workspace_id:
     clusters, contacts, photos, calendar events, graph edges. A
     contact from workspace B never surfaces on a workspace A cluster
     — asserted by ``tests/security/test_scorer_isolation.py``.

  3. **Only non-confirmed clusters, only populated ones.** We skip
     clusters whose ``trusted_person_id`` is already set (review done)
     and clusters with ``member_count < 3`` (too little signal — the
     spec treats these as "below the scoring floor" and reports them
     via ``skipped_small``).

  4. **Transparent scoring.** Each CandidateScore includes a
     ``signals`` dict with the numeric contribution of every weighted
     signal — downstream UI can show "why Alice ranked #1".

  5. **PII-safe logging (ART-14 §4).** Counts, cluster ids, workspace
     id, durations, decision bucket only. Never a contact display_name,
     never an email, never a photo path or raw score.

Signal weights (sum to 1.0):

    co_occurrence   0.50   calendar attendees in ±2h of photo.taken_at
    graph_edge      0.20   prior confirmed link in graph_edges
    photo_name      0.15   fuzzy match of contact name in filename
    temporal        0.10   multi-month cluster span (stability bonus)
    size_bonus      0.05   member_count >= min_cluster_size

A *small-cluster penalty* (×0.5) is applied on top of the linear sum
when ``member_count < min_cluster_size``. This makes the spec's
"clusters with < min_cluster_size get a penalty" layer on top of the
size_bonus signal, rather than cancelling it.

Confidence bucketing (mirrors ART-25 §2 row 8 candidate scoring gate):
  score >= 0.75 → high
  0.50 <= score < 0.75 → medium
  score < 0.50 → low
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.graph_edge import GraphEdge
from api.db.models.photo_asset import PhotoAsset
from api.errors import FaceConsentRequiredError, NotFoundError
from api.services import audit
from api.services.face.clustering_service import get_clustering_params
from api.services.flags import face_pipeline_active
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

# ── Signal weights (sum == 1.0) ────────────────────────────────────────────

W_CO_OCCURRENCE: float = 0.50
W_GRAPH_EDGE: float = 0.20
W_PHOTO_NAME: float = 0.15
W_TEMPORAL: float = 0.10
W_SIZE_BONUS: float = 0.05

SMALL_CLUSTER_PENALTY: float = 0.5
CO_EVENT_WINDOW = timedelta(hours=2)
TEMPORAL_STABILITY_THRESHOLD = timedelta(days=6 * 30)
NAME_FUZZY_THRESHOLD = 0.80

NEEDS_SCORING_PREFIX = "needs_scoring:"
NEEDS_SCORING_TTL_SECS = 30 * 86400  # 30 days


# ── Result shapes ──────────────────────────────────────────────────────────


class CandidateScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    signals: dict[str, float]
    confidence: str  # high | medium | low

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "contact_id": str(self.contact_id),
            "score": round(self.score, 4),
            "signals": {k: round(v, 4) for k, v in self.signals.items()},
            "confidence": self.confidence,
        }


class BatchScoringReport(BaseModel):
    workspace_id: UUID
    scored_clusters: int
    skipped_small: int
    skipped_confirmed: int
    total_candidates_written: int
    duration_ms: int


# ── Confidence bucket ──────────────────────────────────────────────────────


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    """Coerce a datetime to aware-UTC for cross-column comparison.

    ``photo_assets.taken_at`` is TIMESTAMP (naive) and
    ``calendar_events.start_at`` is TIMESTAMPTZ (aware). Direct
    arithmetic between the two would raise — normalize both to UTC
    aware before any comparison.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _confidence(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


# ── Fuzzy name helpers ─────────────────────────────────────────────────────


def _contact_display(contact: Contact) -> str:
    if contact.display_name:
        return contact.display_name.strip()
    parts = [contact.first_name or "", contact.last_name or ""]
    return " ".join(p for p in parts if p).strip()


def _contact_email_set(contact: Contact) -> set[str]:
    emails: set[str] = set()
    if not contact.emails_json:
        return emails
    for entry in contact.emails_json:
        if isinstance(entry, dict):
            raw = entry.get("address") or entry.get("email") or entry.get("value")
        elif isinstance(entry, str):
            raw = entry
        else:
            raw = None
        if isinstance(raw, str) and raw:
            emails.add(raw.lower())
    return emails


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ── Redis: needs_scoring hints (wired from incremental assign) ─────────────


async def mark_cluster_needs_scoring(cluster_id: UUID) -> None:
    """Tag a cluster as eligible for the next batch scoring pass.

    Called from the incremental assigner when a cluster crosses the
    ``member_count >= 3`` threshold. Best-effort: Redis failures are
    swallowed because scoring is advisory and the batch job also
    catches eligible clusters by DB state on each run.
    """
    try:
        r = get_redis(REDIS_DB_CACHE)
        key = f"{NEEDS_SCORING_PREFIX}{cluster_id}"
        await r.set(key, "1", ex=NEEDS_SCORING_TTL_SECS)
    except Exception:
        logger.debug("needs_scoring_mark_failed", exc_info=True)


async def clear_cluster_needs_scoring(cluster_id: UUID) -> None:
    try:
        r = get_redis(REDIS_DB_CACHE)
        await r.delete(f"{NEEDS_SCORING_PREFIX}{cluster_id}")
    except Exception:
        logger.debug("needs_scoring_clear_failed", exc_info=True)


# ── Core: score ONE cluster ────────────────────────────────────────────────


async def score_cluster(
    cluster_id: UUID,
    db: AsyncSession,
    *,
    top_k: int = 5,
    min_cluster_size: int | None = None,
) -> list[CandidateScore]:
    """Score a single face cluster against its workspace's contacts.

    Returns an ordered list of up to ``top_k`` candidates (highest
    score first). Returns an empty list when there is no signal at all
    or when the cluster row cannot be loaded within its workspace.
    """
    cluster = (
        await db.execute(
            select(FaceCluster).where(
                and_(
                    FaceCluster.id == cluster_id,
                    FaceCluster.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if cluster is None:
        raise NotFoundError(
            error_code="FACE_CLUSTER_NOT_FOUND",
            message=f"FaceCluster {cluster_id} not found.",
        )

    workspace_id = cluster.workspace_id
    member_count = int(cluster.member_count or 0)

    if min_cluster_size is None:
        params = await get_clustering_params(workspace_id, db)
        min_cluster_size = params.min_cluster_size

    # Member face_detections → (photo_asset_id, taken_at, filename) rows.
    rows = (
        await db.execute(
            select(
                PhotoAsset.id,
                PhotoAsset.taken_at,
                File.filename,
            )
            .join(FaceDetection, FaceDetection.photo_asset_id == PhotoAsset.id)
            .join(File, File.id == PhotoAsset.file_id)
            .where(
                and_(
                    FaceDetection.cluster_id == cluster_id,
                    FaceDetection.workspace_id == workspace_id,
                    PhotoAsset.workspace_id == workspace_id,
                )
            )
        )
    ).all()

    if not rows:
        return []

    photo_times = [
        _as_aware_utc(r.taken_at) for r in rows if r.taken_at is not None
    ]
    filenames = [r.filename or "" for r in rows]
    total_members = max(len(rows), 1)

    # Load all workspace contacts once — cheap on personal-scale data.
    contacts = (
        (
            await db.execute(
                select(Contact).where(
                    and_(
                        Contact.workspace_id == workspace_id,
                        Contact.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    if not contacts:
        return []

    contact_by_id: dict[UUID, Contact] = {c.id: c for c in contacts}
    display_by_id: dict[UUID, str] = {
        c.id: _contact_display(c) for c in contacts
    }
    emails_by_id: dict[UUID, set[str]] = {
        c.id: _contact_email_set(c) for c in contacts
    }

    # ── Signal A: co-occurrence via calendar events ────────────────────
    co_hits: dict[UUID, int] = defaultdict(int)
    if photo_times:
        earliest = min(photo_times) - CO_EVENT_WINDOW
        latest = max(photo_times) + CO_EVENT_WINDOW
        events = (
            (
                await db.execute(
                    select(CalendarEvent).where(
                        and_(
                            CalendarEvent.workspace_id == workspace_id,
                            CalendarEvent.start_at >= earliest,
                            CalendarEvent.start_at <= latest,
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        for row_taken_at in photo_times:
            low = row_taken_at - CO_EVENT_WINDOW
            high = row_taken_at + CO_EVENT_WINDOW
            for ev in events:
                ev_start = _as_aware_utc(ev.start_at)
                if ev_start is None or ev_start < low or ev_start > high:
                    continue
                participants = ev.participants_json or []
                matched_ids: set[UUID] = set()
                for p in participants:
                    matched_ids.update(
                        _match_participant(p, emails_by_id, display_by_id)
                    )
                for cid in matched_ids:
                    co_hits[cid] += 1

    # ── Signal B: graph_edges (prior confirmations) ─────────────────────
    edges = (
        (
            await db.execute(
                select(GraphEdge).where(
                    and_(
                        GraphEdge.workspace_id == workspace_id,
                        GraphEdge.from_type == "face_cluster",
                        GraphEdge.from_id == cluster_id,
                        GraphEdge.to_type == "contact",
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    edge_contact_ids: set[UUID] = {
        e.to_id for e in edges if e.to_id in contact_by_id
    }

    # ── Signal C: photo metadata (filename fuzzy match) ─────────────────
    name_hits: dict[UUID, int] = defaultdict(int)
    for fname in filenames:
        if not fname:
            continue
        stem = fname.rsplit(".", 1)[0]
        for cid, display in display_by_id.items():
            if not display:
                continue
            if _name_similarity(stem, display) >= NAME_FUZZY_THRESHOLD:
                name_hits[cid] += 1

    # ── Signal D: temporal stability ────────────────────────────────────
    temporal_bonus_eligible = False
    if len(photo_times) >= 2:
        span = max(photo_times) - min(photo_times)
        temporal_bonus_eligible = span >= TEMPORAL_STABILITY_THRESHOLD

    # ── Signal E: size bonus ────────────────────────────────────────────
    size_bonus_value = 1.0 if member_count >= min_cluster_size else 0.0
    small_cluster = member_count < min_cluster_size

    # ── Combine into per-contact scores ─────────────────────────────────
    candidate_ids: set[UUID] = (
        set(co_hits) | set(edge_contact_ids) | set(name_hits)
    )
    if not candidate_ids:
        return []

    scores: list[CandidateScore] = []
    for cid in candidate_ids:
        co_norm = min(co_hits.get(cid, 0) / total_members, 1.0)
        edge_norm = 1.0 if cid in edge_contact_ids else 0.0
        name_norm = min(name_hits.get(cid, 0) / total_members, 1.0)
        # temporal: small flat bonus given only to the top co-occurrence
        # contact — applied after ranking. Placeholder 0.0 here.
        temporal_norm = 0.0
        raw = (
            W_CO_OCCURRENCE * co_norm
            + W_GRAPH_EDGE * edge_norm
            + W_PHOTO_NAME * name_norm
            + W_TEMPORAL * temporal_norm
            + W_SIZE_BONUS * size_bonus_value
        )
        scores.append(
            CandidateScore(
                contact_id=cid,
                score=raw,
                signals={
                    "co_occurrence": co_norm,
                    "graph_edge": edge_norm,
                    "photo_name": name_norm,
                    "temporal": temporal_norm,
                    "size_bonus": size_bonus_value,
                },
                confidence=_confidence(raw),
            )
        )

    scores.sort(key=lambda s: s.score, reverse=True)

    # Temporal bonus → the top co-occurrence contact gets the full
    # W_TEMPORAL component. We intentionally add this *after* the sort
    # so ties remain deterministic based on co-occurrence density.
    if temporal_bonus_eligible:
        top_co_cid: UUID | None = None
        top_co_hits = 0
        for cid, hits in co_hits.items():
            if hits > top_co_hits:
                top_co_cid = cid
                top_co_hits = hits
        if top_co_cid is not None:
            for i, s in enumerate(scores):
                if s.contact_id == top_co_cid:
                    new_signals = dict(s.signals)
                    new_signals["temporal"] = 1.0
                    new_raw = min(s.score + W_TEMPORAL, 1.0)
                    scores[i] = CandidateScore(
                        contact_id=s.contact_id,
                        score=new_raw,
                        signals=new_signals,
                        confidence=_confidence(new_raw),
                    )
                    break
            scores.sort(key=lambda s: s.score, reverse=True)

    # Small-cluster penalty: halve *all* scores if the cluster is below
    # its workspace's min_cluster_size. The spec treats this as a
    # blanket "this cluster is too small to trust" modifier.
    if small_cluster:
        scores = [
            CandidateScore(
                contact_id=s.contact_id,
                score=s.score * SMALL_CLUSTER_PENALTY,
                signals=s.signals,
                confidence=_confidence(s.score * SMALL_CLUSTER_PENALTY),
            )
            for s in scores
        ]

    return scores[:top_k]


def _match_participant(
    participant: Any,
    emails_by_id: dict[UUID, set[str]],
    display_by_id: dict[UUID, str],
) -> set[UUID]:
    """Return contact ids matching one calendar participant blob.

    The participants_json shape is source-dependent; we defensively
    look for email, address, name, or display_name fields. Email
    matches are exact (case-insensitive); name matches use the same
    fuzzy threshold as photo filenames.
    """
    if not isinstance(participant, dict):
        if isinstance(participant, str):
            email = participant.lower() if "@" in participant else None
            name = participant if email is None else None
        else:
            return set()
    else:
        email_raw = (
            participant.get("email")
            or participant.get("address")
            or participant.get("mail")
        )
        name = (
            participant.get("name")
            or participant.get("display_name")
            or participant.get("displayName")
        )
        email = email_raw.lower() if isinstance(email_raw, str) else None

    matched: set[UUID] = set()
    if email:
        for cid, emails in emails_by_id.items():
            if email in emails:
                matched.add(cid)
    if not matched and isinstance(name, str) and name.strip():
        for cid, display in display_by_id.items():
            if display and _name_similarity(name, display) >= NAME_FUZZY_THRESHOLD:
                matched.add(cid)
    return matched


# ── Batch: score every eligible cluster in a workspace ────────────────────


async def score_workspace_clusters(
    workspace_id: UUID,
    db: AsyncSession,
) -> BatchScoringReport:
    """Score all unconfirmed clusters in a workspace and cache results.

    Eligibility: ``deleted_at IS NULL``, ``trusted_person_id IS NULL``,
    ``cluster_state = 'unconfirmed'``, ``member_count >= 3``. Clusters
    failing one of the first three filters are skipped silently.
    Clusters failing only the member_count floor are counted in
    ``skipped_small``.

    Consent is re-checked *inside* this function so a revoke landing
    between rate-limit acquisition and execution still fails closed.
    """
    if not await face_pipeline_active(workspace_id, db):
        raise FaceConsentRequiredError(
            error_code="FACE_CONSENT_REQUIRED",
            message="Face pipeline consent is required.",
        )

    t0 = time.monotonic()
    params = await get_clustering_params(workspace_id, db)

    clusters = (
        (
            await db.execute(
                select(FaceCluster).where(
                    and_(
                        FaceCluster.workspace_id == workspace_id,
                        FaceCluster.deleted_at.is_(None),
                        FaceCluster.trusted_person_id.is_(None),
                        FaceCluster.cluster_state == "unconfirmed",
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    scored = 0
    skipped_small = 0
    skipped_confirmed = 0
    total_candidates = 0

    for cluster in clusters:
        if int(cluster.member_count or 0) < 3:
            skipped_small += 1
            continue
        try:
            candidates = await score_cluster(
                cluster.id,
                db,
                top_k=5,
                min_cluster_size=params.min_cluster_size,
            )
        except Exception:
            logger.warning(
                "candidate_score_cluster_failed",
                workspace_id=str(workspace_id),
                cluster_id=str(cluster.id),
                exc_info=True,
            )
            continue
        cluster.candidates_json = [c.to_jsonable() for c in candidates]
        scored += 1
        total_candidates += len(candidates)
        await clear_cluster_needs_scoring(cluster.id)

    await db.flush()

    duration_ms = int((time.monotonic() - t0) * 1000)

    await audit.log_event(
        db=db,
        action="face_candidates_scored",
        object_type="face_clusters",
        workspace_id=workspace_id,
        metadata={
            "scored_clusters": scored,
            "skipped_small": skipped_small,
            "total_candidates": total_candidates,
            "duration_ms": duration_ms,
        },
    )

    logger.info(
        "face_candidate_scoring_complete",
        workspace_id=str(workspace_id),
        scored_clusters=scored,
        skipped_small=skipped_small,
        total_candidates=total_candidates,
        duration_ms=duration_ms,
    )

    return BatchScoringReport(
        workspace_id=workspace_id,
        scored_clusters=scored,
        skipped_small=skipped_small,
        skipped_confirmed=skipped_confirmed,
        total_candidates_written=total_candidates,
        duration_ms=duration_ms,
    )
