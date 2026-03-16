from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ResponseMeta(BaseModel):
    requestId: UUID
    generatedAt: datetime
    stub: bool = True
    workspaceId: str | None = None


class Problem(BaseModel):
    code: str
    message: str
    suggestion: str | None = None


class ProblemResponse(BaseModel):
    meta: ResponseMeta
    error: Problem


class HealthCheck(BaseModel):
    name: str
    status: Literal["ok", "warning", "planned"]
    detail: str


class HealthData(BaseModel):
    status: Literal["ok", "warning"]
    summary: str
    checks: list[HealthCheck]


class HealthResponse(BaseModel):
    meta: ResponseMeta
    data: HealthData


class VersionData(BaseModel):
    applicationVersion: str
    apiVersion: str
    contractVersion: str
    buildChannel: str


class VersionResponse(BaseModel):
    meta: ResponseMeta
    data: VersionData


class AgendaItem(BaseModel):
    title: str
    startsAt: datetime
    source: str


class AgendaCard(BaseModel):
    id: str
    type: Literal["agenda"]
    title: str
    items: list[AgendaItem]


class FocusCard(BaseModel):
    id: str
    type: Literal["focus"]
    title: str
    detail: str
    actionLabel: str


class SystemCard(BaseModel):
    id: str
    type: Literal["system"]
    title: str
    detail: str
    status: Literal["planned", "warming", "healthy", "warning"]


TodayCard = Annotated[AgendaCard | FocusCard | SystemCard, Field(discriminator="type")]


class TodayData(BaseModel):
    workspaceId: str
    date: date
    summary: str
    cards: list[TodayCard]


class TodayResponse(BaseModel):
    meta: ResponseMeta
    data: TodayData


class RecapWindow(BaseModel):
    label: str
    start: datetime
    end: datetime


class RecapHighlight(BaseModel):
    title: str
    detail: str
    category: Literal["capture", "calendar", "people", "system"]


class RecapStats(BaseModel):
    itemsProcessed: int
    suggestionsReady: int
    remindersDue: int


class RecapData(BaseModel):
    workspaceId: str
    window: RecapWindow
    narrative: str
    highlights: list[RecapHighlight]
    stats: RecapStats


class RecapResponse(BaseModel):
    meta: ResponseMeta
    data: RecapData


class JobProgress(BaseModel):
    completedUnits: int
    totalUnits: int


class JobStatusData(BaseModel):
    jobId: str
    kind: str
    status: Literal["queued", "running", "completed"]
    detail: str
    progress: JobProgress
    updatedAt: datetime


class JobStatusResponse(BaseModel):
    meta: ResponseMeta
    data: JobStatusData
