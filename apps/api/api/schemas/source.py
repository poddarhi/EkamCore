from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


SourceType = Literal["local_folder", "photo_folder", "contacts", "calendar", "reminders"]
SourceStatus = Literal["active", "paused"]

_FOLDER_TYPES: frozenset[str] = frozenset({"local_folder", "photo_folder"})


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: SourceType
    path: str | None = None
    config_json: dict | None = None


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: SourceStatus | None = None
    config_json: dict | None = None


class SourceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    workspace_id: UUID
    name: str
    type: str
    path: str | None
    config_json: dict | None
    status: str
    last_sync_at: datetime | None
    registered_by: UUID
    created_at: datetime
    updated_at: datetime


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    next_cursor: str | None
