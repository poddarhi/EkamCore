"""ResponseEnvelope schema: standard wrapper for all interactive API endpoints.

All query/today/search endpoints return this structure so the frontend
and mobile clients can handle cards, sources, and actions uniformly.

Non-interactive endpoints (health, auth, CRUD) return their own schemas.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Card subtypes (discriminated union on `type`)
# ---------------------------------------------------------------------------


class EventCard(BaseModel):
    type: Literal["event"] = "event"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


class ReminderCard(BaseModel):
    type: Literal["reminder"] = "reminder"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


class StatusCard(BaseModel):
    type: Literal["status"] = "status"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


class PersonCard(BaseModel):
    """Phase 3: People Graph cards (S11+)."""

    type: Literal["person"] = "person"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


class FileCard(BaseModel):
    """Phase 2: File ingestion cards (S07+)."""

    type: Literal["file"] = "file"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


class PhotoCard(BaseModel):
    """Phase 2: Photo cards (S09+)."""

    type: Literal["photo"] = "photo"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


class SuggestionCard(BaseModel):
    type: Literal["suggestion"] = "suggestion"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


class PackCard(BaseModel):
    """Pack-generated composite cards (S11+)."""

    type: Literal["pack"] = "pack"
    id: UUID
    priority_score: float = 0.0
    source_ids: list[UUID] = []
    payload: dict[str, Any] = {}


Card = Annotated[
    EventCard
    | ReminderCard
    | StatusCard
    | PersonCard
    | FileCard
    | PhotoCard
    | SuggestionCard
    | PackCard,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Source reference
# ---------------------------------------------------------------------------


class SourceRef(BaseModel):
    type: Literal["file", "contact", "event", "reminder", "photo", "person"]
    id: UUID
    title: str
    relevance: float = 1.0


# ---------------------------------------------------------------------------
# Suggested action
# ---------------------------------------------------------------------------


class SuggestedAction(BaseModel):
    action_type: str
    label: str
    payload: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class CacheHint(BaseModel):
    ttl_seconds: int


class ResponseMetadata(BaseModel):
    query_path: Literal[
        "deterministic", "semantic", "small_model", "large_model"
    ] = "deterministic"
    latency_ms: int = 0
    is_partial: bool = False
    cache_hint: CacheHint | None = None


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


class ResponseEnvelope(BaseModel):
    answer_text: str | None = None
    confidence_level: Literal["deterministic", "high", "medium", "low"] = "deterministic"
    sources: list[SourceRef] = []
    cards: list[Card] = []
    suggested_actions: list[SuggestedAction] = []
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_envelope(
    *,
    cards: list[Card] | None = None,
    sources: list[SourceRef] | None = None,
    suggested_actions: list[SuggestedAction] | None = None,
    answer_text: str | None = None,
    confidence_level: Literal[
        "deterministic", "high", "medium", "low"
    ] = "deterministic",
    query_path: Literal[
        "deterministic", "semantic", "small_model", "large_model"
    ] = "deterministic",
    latency_ms: int = 0,
    is_partial: bool = False,
    cache_hint: CacheHint | None = None,
) -> ResponseEnvelope:
    """Construct a ResponseEnvelope with sensible defaults."""
    return ResponseEnvelope(
        answer_text=answer_text,
        confidence_level=confidence_level,
        sources=sources or [],
        cards=cards or [],
        suggested_actions=suggested_actions or [],
        metadata=ResponseMetadata(
            query_path=query_path,
            latency_ms=latency_ms,
            is_partial=is_partial,
            cache_hint=cache_hint,
        ),
    )
