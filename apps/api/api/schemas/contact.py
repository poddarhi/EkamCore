from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class ContactInput(BaseModel):
    external_id: str = Field(min_length=1, max_length=500)
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    emails_json: list | None = None
    phones_json: list | None = None
    addresses_json: list | None = None
    organization: str | None = None
    job_title: str | None = None
    birthday: date | None = None
    notes: str | None = None


class ContactIngestRequest(BaseModel):
    workspace_id: UUID
    source_id: UUID
    contacts: list[ContactInput] = Field(min_length=0)


class ContactIngestResponse(BaseModel):
    inserted: int
    updated: int
    unchanged: int
    trusted_persons_created: int
