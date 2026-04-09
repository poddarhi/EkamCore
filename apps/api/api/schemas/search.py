"""Request/response schemas for the search endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PaginationInfo(BaseModel):
    cursor: int  # Offset for next page
    has_more: bool


class SearchResponse(BaseModel):
    data: list[dict[str, Any]]  # Serialized Card objects
    pagination: PaginationInfo
    facets: dict[str, int]  # type_name → total count
