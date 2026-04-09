from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ReminderInput(BaseModel):
    external_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    completed_at: datetime | None = None
    is_completed: bool = False
    priority: Literal["high", "medium", "low", "none"] = "none"
    list_name: str | None = None
    notes: str | None = None


class ReminderIngestRequest(BaseModel):
    workspace_id: UUID
    source_id: UUID
    reminders: list[ReminderInput] = Field(min_length=0)


class ReminderIngestResponse(BaseModel):
    inserted: int
    updated: int
    unchanged: int


# ── Write-through (user-created reminders) ──


class ReminderCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: Literal["high", "medium", "low", "none"] = "none"
    list_name: str | None = Field(None, max_length=255)
    notes: str | None = None


class ReminderResponse(BaseModel):
    id: UUID
    title: str
    due_at: datetime | None
    priority: str
    list_name: str | None
    notes: str | None
    is_completed: bool
    write_through_status: str
    created_at: datetime

    model_config = {"from_attributes": True}
