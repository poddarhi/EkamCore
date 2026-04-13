"""Schemas for merge/split/undo endpoints (S12-006)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MergeRequest(BaseModel):
    person_ids: list[UUID] = Field(min_length=2)
    keeper_id: UUID


class SplitRequest(BaseModel):
    face_detection_ids: list[UUID] = Field(min_length=1)
    new_display_name: str = Field(min_length=1, max_length=255)


class OperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    user_id: UUID
    operation_type: str
    forward_payload: dict[str, Any]
    created_at: datetime
    undone_at: datetime | None = None
    undone_by_user_id: UUID | None = None


class OperationListResponse(BaseModel):
    items: list[OperationResponse]


class UndoResponse(BaseModel):
    operation_id: UUID
    operation_type: str
