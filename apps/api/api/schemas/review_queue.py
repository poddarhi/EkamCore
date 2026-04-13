"""Pydantic schemas for the Review Queue API (S12-005)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReviewCandidate(BaseModel):
    """One candidate contact as surfaced to the review UI.

    Mirrors ``candidate_scorer.CandidateScore.to_jsonable()`` shape
    but is re-declared here so the review queue response stays
    decoupled from the scoring pipeline's internal pydantic model.
    """

    model_config = ConfigDict(extra="ignore")

    contact_id: UUID
    score: float
    signals: dict[str, float] = {}
    confidence: str


class ReviewQueueItem(BaseModel):
    cluster_id: UUID
    member_count: int
    sample_face_detection_ids: list[UUID]
    sample_photo_asset_ids: list[UUID]
    top_candidate: ReviewCandidate | None = None
    other_candidates: list[ReviewCandidate] = []
    confidence_bucket: str  # high | medium | low | none
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class ReviewQueueListResponse(BaseModel):
    items: list[ReviewQueueItem]
    next_cursor: str | None = None


class ReviewQueueDetailResponse(BaseModel):
    """Detail response: every member face_detection + photo_asset,
    not just the preview sample."""

    cluster_id: UUID
    member_count: int
    face_detection_ids: list[UUID]
    photo_asset_ids: list[UUID]
    top_candidate: ReviewCandidate | None = None
    other_candidates: list[ReviewCandidate] = []
    confidence_bucket: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
