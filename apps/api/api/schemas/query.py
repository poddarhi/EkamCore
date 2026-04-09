"""Request/response schemas for the query endpoint."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Natural language query")
    workspace_id: UUID = Field(..., description="Workspace to query")
    prefer_fast: bool = Field(False, description="Skip LLM, use deterministic only")
