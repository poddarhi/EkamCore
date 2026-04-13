"""Pydantic schemas for the TrustedPersons API (S12-004)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TrustedPersonResponse(BaseModel):
    """One row returned by the People API. Shape mirrors the ORM
    model minus the FK-cascade fields the client doesn't need."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    display_name: str
    canonical_contact_id: UUID | None = None
    trust_source: str
    confirmed_at: datetime | None = None
    confirmed_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TrustedPersonListResponse(BaseModel):
    items: list[TrustedPersonResponse]
    next_cursor: str | None = None


class TrustedPersonCreateRequest(BaseModel):
    """POST /api/v1/people — create a trusted person from a cluster."""

    cluster_id: UUID
    display_name: str = Field(min_length=1, max_length=255)
    canonical_contact_id: UUID | None = None


class TrustedPersonRenameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class ConfirmCandidateRequest(BaseModel):
    cluster_id: UUID
    contact_id: UUID


class RejectClusterRequest(BaseModel):
    cluster_id: UUID
    reason: str | None = Field(default=None, max_length=500)
