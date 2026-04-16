"""Pydantic schemas for the photo lightbox face overlay (S13-008)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class PhotoFaceItem(BaseModel):
    face_detection_id: UUID
    bbox: dict[str, float]
    detection_score: float
    cluster_id: UUID | None = None
    trusted_person_id: UUID | None = None
    trusted_person_display_name: str | None = None
    trusted_person_avatar_url: str | None = None


class PhotoFacesResponse(BaseModel):
    items: list[PhotoFaceItem]
