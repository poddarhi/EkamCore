from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CalendarEventInput(BaseModel):
    external_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    start_at: datetime
    end_at: datetime | None = None
    is_all_day: bool = False
    location: str | None = None
    participants_json: list | None = None
    recurrence_rule: str | None = None
    calendar_name: str | None = None
    notes: str | None = None


class CalendarIngestRequest(BaseModel):
    workspace_id: UUID
    source_id: UUID
    events: list[CalendarEventInput] = Field(min_length=0)


class CalendarIngestResponse(BaseModel):
    inserted: int
    updated: int
    unchanged: int
