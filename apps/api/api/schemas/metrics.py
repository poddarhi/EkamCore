"""Pydantic schemas for metrics API (G-15 / ART-27)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MetricEntry(BaseModel):
    id: UUID
    metric_key: str
    metric_value: dict[str, Any]
    period_start: datetime
    period_end: datetime
    workspace_id: UUID
    created_at: datetime


class MetricsResponse(BaseModel):
    metrics: list[MetricEntry] = Field(default_factory=list)
    count: int
    period: str | None = None


class CurrentMetricsSnapshot(BaseModel):
    timestamp: datetime
    workspace_id: UUID
    usage_today: dict[str, int] = Field(default_factory=dict)
    latency_current_hour: dict[str, dict[str, float]] = Field(default_factory=dict)
    cumulative: dict[str, int] = Field(default_factory=dict)
