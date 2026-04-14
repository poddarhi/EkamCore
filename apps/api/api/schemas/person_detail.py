"""Pydantic schemas for the Person detail page (S13-003).

Six list-style endpoints + a remove-face mutation feed the
PersonDetailPage tabs and the faces management grid.

Reminders and files currently return empty lists — the underlying
linkage tables (reminder→person and the paperless correspondent
bridge) have not landed yet. The shapes are defined now so the
client and OpenAPI contract are stable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class _PaginatedBase(BaseModel):
    next_cursor: str | None = None


# ── Photos ────────────────────────────────────────────────────────────────


class PersonPhotoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_id: UUID
    thumbnail_url: str
    taken_at: datetime | None = None
    face_count: int = 0
    width: int | None = None
    height: int | None = None


class PersonPhotoListResponse(_PaginatedBase):
    items: list[PersonPhotoItem]


# ── Files ─────────────────────────────────────────────────────────────────


class PersonFileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime


class PersonFileListResponse(_PaginatedBase):
    items: list[PersonFileItem]


# ── Events ────────────────────────────────────────────────────────────────


class PersonEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    start_at: datetime
    end_at: datetime | None = None
    location: str | None = None
    is_all_day: bool = False


class PersonEventListResponse(_PaginatedBase):
    items: list[PersonEventItem]


# ── Reminders ─────────────────────────────────────────────────────────────


class PersonReminderItem(BaseModel):
    """Placeholder shape — reminders have no person linkage in v1.0
    so this endpoint returns an empty list. Defined now so the OpenAPI
    contract is stable when the bridge story lands."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    due_at: datetime | None = None
    priority: str = "none"
    completed_at: datetime | None = None
    is_completed: bool = False


class PersonReminderListResponse(_PaginatedBase):
    items: list[PersonReminderItem]


# ── Faces (for the faces-management grid) ─────────────────────────────────


class PersonFaceItem(BaseModel):
    face_detection_id: UUID
    photo_asset_id: UUID
    cluster_id: UUID
    detection_score: float
    thumbnail_url: str


class PersonFacesResponse(BaseModel):
    items: list[PersonFaceItem]


# ── Remove-face request ───────────────────────────────────────────────────


class RemoveFaceRequest(BaseModel):
    face_detection_id: UUID
