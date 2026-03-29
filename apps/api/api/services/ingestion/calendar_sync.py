"""Calendar event import service: upsert by external_id with change detection."""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.source import Source
from api.errors import NotFoundError, ValidationError
from api.schemas.calendar import CalendarEventInput

logger = structlog.get_logger()


def _to_utc(dt: datetime) -> datetime:
    """Normalise to UTC-aware datetime for comparison."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _event_changed(row: CalendarEvent, ev: CalendarEventInput) -> bool:
    """Return True if any mutable field differs between the stored row and the incoming event."""
    if row.title != ev.title:
        return True
    if _to_utc(row.start_at) != _to_utc(ev.start_at):
        return True
    stored_end = _to_utc(row.end_at) if row.end_at else None
    incoming_end = _to_utc(ev.end_at) if ev.end_at else None
    if stored_end != incoming_end:
        return True
    if row.is_all_day != ev.is_all_day:
        return True
    if row.location != ev.location:
        return True
    if row.participants_json != ev.participants_json:
        return True
    if row.recurrence_rule != ev.recurrence_rule:
        return True
    if row.calendar_name != ev.calendar_name:
        return True
    if row.notes != ev.notes:
        return True
    return False


def _apply_event(row: CalendarEvent, ev: CalendarEventInput) -> None:
    """Overwrite mutable fields on an existing row from the incoming event."""
    row.title = ev.title
    row.start_at = ev.start_at
    row.end_at = ev.end_at
    row.is_all_day = ev.is_all_day
    row.location = ev.location
    row.participants_json = ev.participants_json
    row.recurrence_rule = ev.recurrence_rule
    row.calendar_name = ev.calendar_name
    row.notes = ev.notes


async def upsert_events(
    source_id: UUID,
    workspace_id: UUID,
    events: list[CalendarEventInput],
    db: AsyncSession,
) -> tuple[int, int, int]:
    """Upsert calendar events for a source.

    Returns (inserted, updated, unchanged).

    Validates that source_id belongs to workspace_id.
    Deduplicates incoming events by external_id (last occurrence wins).
    Updates source.last_sync_at on completion.
    """
    # Validate source ownership
    source_stmt = select(Source).where(
        Source.id == source_id,
        Source.workspace_id == workspace_id,
        Source.deleted_at.is_(None),
    )
    source = (await db.execute(source_stmt)).scalar_one_or_none()
    if not source:
        raise NotFoundError(error_code="SOURCE_NOT_FOUND", message="Source not found for this workspace.")

    if source.type != "calendar":
        raise ValidationError(
            error_code="SOURCE_TYPE_MISMATCH",
            message=f"Expected source type 'calendar', got '{source.type}'.",
        )

    # Deduplicate incoming events by external_id (last occurrence wins)
    deduped: dict[str, CalendarEventInput] = {}
    for ev in events:
        deduped[ev.external_id] = ev

    if not deduped:
        source.last_sync_at = datetime.now(timezone.utc)
        await db.flush()
        return 0, 0, 0

    # Load existing events for this source
    existing_stmt = select(CalendarEvent).where(
        CalendarEvent.source_id == source_id,
        CalendarEvent.workspace_id == workspace_id,
    )
    existing: dict[str, CalendarEvent] = {
        row.external_id: row
        for row in (await db.execute(existing_stmt)).scalars().all()
    }

    inserted = updated = unchanged = 0

    for external_id, ev in deduped.items():
        if external_id not in existing:
            db.add(CalendarEvent(
                workspace_id=workspace_id,
                source_id=source_id,
                external_id=external_id,
                title=ev.title,
                start_at=ev.start_at,
                end_at=ev.end_at,
                is_all_day=ev.is_all_day,
                location=ev.location,
                participants_json=ev.participants_json,
                recurrence_rule=ev.recurrence_rule,
                calendar_name=ev.calendar_name,
                notes=ev.notes,
            ))
            inserted += 1
        elif _event_changed(existing[external_id], ev):
            _apply_event(existing[external_id], ev)
            updated += 1
        else:
            unchanged += 1

    source.last_sync_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "calendar_events_upserted",
        source_id=str(source_id),
        workspace_id=str(workspace_id),
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
    )
    return inserted, updated, unchanged
