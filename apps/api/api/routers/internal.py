"""Internal API endpoints — not routed by Caddy, accessible within the container network only."""

from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.schemas.calendar import CalendarIngestRequest, CalendarIngestResponse
from api.schemas.contact import ContactIngestRequest, ContactIngestResponse
from api.schemas.reminder import ReminderIngestRequest, ReminderIngestResponse
from api.services.ingestion import calendar_sync, contact_sync, reminder_sync
from api.services.ingestion.fs_handler import handle_fs_event, scan_source

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


@router.post("/ingest/calendar", response_model=CalendarIngestResponse)
async def ingest_calendar(
    body: CalendarIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> CalendarIngestResponse:
    """Upsert calendar events for a source.

    Called by scheduled tasks or the Tauri manager app (future).
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    inserted, updated, unchanged = await calendar_sync.upsert_events(
        source_id=body.source_id,
        workspace_id=body.workspace_id,
        events=body.events,
        db=db,
    )
    return CalendarIngestResponse(inserted=inserted, updated=updated, unchanged=unchanged)


@router.post("/ingest/reminders", response_model=ReminderIngestResponse)
async def ingest_reminders(
    body: ReminderIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> ReminderIngestResponse:
    """Upsert reminders for a source.

    Called by scheduled tasks or the Tauri manager app (future).
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    inserted, updated, unchanged = await reminder_sync.upsert_reminders(
        source_id=body.source_id,
        workspace_id=body.workspace_id,
        reminders=body.reminders,
        db=db,
    )
    return ReminderIngestResponse(inserted=inserted, updated=updated, unchanged=unchanged)


@router.post("/ingest/contacts", response_model=ContactIngestResponse)
async def ingest_contacts(
    body: ContactIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> ContactIngestResponse:
    """Upsert contacts for a source. High-quality contacts auto-create a TrustedPerson
    when the trusted_persons table exists (Phase 3 feature gate).

    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    inserted, updated, unchanged, trusted_persons_created = await contact_sync.upsert_contacts(
        source_id=body.source_id,
        workspace_id=body.workspace_id,
        contacts=body.contacts,
        db=db,
    )
    return ContactIngestResponse(
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        trusted_persons_created=trusted_persons_created,
    )


# ---------------------------------------------------------------------------
# Filesystem event endpoints
# ---------------------------------------------------------------------------


class FsEventRequest(BaseModel):
    source_id: UUID
    event_type: Literal["created", "modified", "deleted", "renamed"]
    path: str = Field(min_length=1, max_length=4096)
    old_path: str | None = Field(None, max_length=4096)


class FsScanRequest(BaseModel):
    source_id: UUID


@router.post("/fs-event", status_code=202)
async def post_fs_event(
    body: FsEventRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive a filesystem change event from the manager app.

    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    result = await handle_fs_event(
        source_id=body.source_id,
        event_type=body.event_type,
        path=body.path,
        old_path=body.old_path,
        db=db,
    )

    logger.info(
        "fs_event_received",
        source_id=str(body.source_id),
        event_type=body.event_type,
        action=result.get("action"),
    )
    return result


@router.post("/fs-scan", status_code=202)
async def post_fs_scan(
    body: FsScanRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a full filesystem scan for a source.

    Compares the source path to the files table:
    - New files → queued for ingestion
    - Missing files → marked as deleted
    - Existing files → untouched

    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    result = await scan_source(source_id=body.source_id, db=db)

    logger.info(
        "fs_scan_triggered",
        source_id=str(body.source_id),
        new=result.get("new"),
        deleted=result.get("deleted"),
    )
    return result
