"""Pydantic models for the PaperlessNGX REST API v3 response shapes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PaperlessCorrespondent(BaseModel):
    id: int
    name: str
    slug: str = ""
    match: str = ""
    matching_algorithm: int = 0
    is_insensitive: bool = False
    document_count: int = 0


class PaperlessTag(BaseModel):
    id: int
    name: str
    slug: str = ""
    colour: int = 0
    match: str = ""
    matching_algorithm: int = 0
    is_insensitive: bool = False
    is_inbox_tag: bool = False
    document_count: int = 0


class PaperlessDocType(BaseModel):
    id: int
    name: str
    slug: str = ""
    match: str = ""
    matching_algorithm: int = 0
    is_insensitive: bool = False
    document_count: int = 0


class PaperlessDocument(BaseModel):
    """A Paperless document.

    The API returns ``correspondent`` (int), ``document_type`` (int), and
    ``tags`` (list[int]).  We map them to the more descriptive
    ``correspondent_id``, ``document_type_id``, and ``tag_ids`` via aliases
    so callers always use the verbose names.
    """

    id: int
    title: str
    content: str = ""
    correspondent_id: int | None = Field(None, alias="correspondent")
    document_type_id: int | None = Field(None, alias="document_type")
    tag_ids: list[int] = Field(default_factory=list, alias="tags")
    created: datetime | None = None
    modified: datetime | None = None
    added: datetime | None = None
    archive_serial_number: int | None = None
    original_file_name: str | None = None

    model_config = {"populate_by_name": True}


class PaperlessSearchResult(BaseModel):
    count: int
    next: str | None = None
    previous: str | None = None
    results: list[PaperlessDocument] = Field(default_factory=list)
