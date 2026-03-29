"""Reminder import service: upsert by external_id with change detection."""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.reminder import Reminder
from api.db.models.source import Source
from api.errors import NotFoundError, ValidationError
from api.schemas.reminder import ReminderInput

logger = structlog.get_logger()


def _to_utc(dt: datetime) -> datetime:
    """Normalise to UTC-aware datetime for comparison."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _reminder_changed(row: Reminder, rem: ReminderInput) -> bool:
    """Return True if any mutable field differs between the stored row and the incoming reminder."""
    if row.title != rem.title:
        return True
    stored_due = _to_utc(row.due_at) if row.due_at else None
    incoming_due = _to_utc(rem.due_at) if rem.due_at else None
    if stored_due != incoming_due:
        return True
    stored_completed = _to_utc(row.completed_at) if row.completed_at else None
    incoming_completed = _to_utc(rem.completed_at) if rem.completed_at else None
    if stored_completed != incoming_completed:
        return True
    if row.is_completed != rem.is_completed:
        return True
    if row.priority != rem.priority:
        return True
    if row.list_name != rem.list_name:
        return True
    if row.notes != rem.notes:
        return True
    return False


def _apply_reminder(row: Reminder, rem: ReminderInput) -> None:
    """Overwrite mutable fields on an existing row from the incoming reminder."""
    row.title = rem.title
    row.due_at = rem.due_at
    row.completed_at = rem.completed_at
    row.is_completed = rem.is_completed
    row.priority = rem.priority
    row.list_name = rem.list_name
    row.notes = rem.notes


async def upsert_reminders(
    source_id: UUID,
    workspace_id: UUID,
    reminders: list[ReminderInput],
    db: AsyncSession,
) -> tuple[int, int, int]:
    """Upsert reminders for a source.

    Returns (inserted, updated, unchanged).

    Validates that source_id belongs to workspace_id.
    Deduplicates incoming reminders by external_id (last occurrence wins).
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

    if source.type != "reminders":
        raise ValidationError(
            error_code="SOURCE_TYPE_MISMATCH",
            message=f"Expected source type 'reminders', got '{source.type}'.",
        )

    # Deduplicate incoming reminders by external_id (last occurrence wins)
    deduped: dict[str, ReminderInput] = {}
    for rem in reminders:
        deduped[rem.external_id] = rem

    if not deduped:
        source.last_sync_at = datetime.now(timezone.utc)
        await db.flush()
        return 0, 0, 0

    # Load existing reminders for this source
    existing_stmt = select(Reminder).where(
        Reminder.source_id == source_id,
        Reminder.workspace_id == workspace_id,
        Reminder.deleted_at.is_(None),
    )
    existing: dict[str, Reminder] = {
        row.external_id: row
        for row in (await db.execute(existing_stmt)).scalars().all()
        if row.external_id is not None
    }

    inserted = updated = unchanged = 0

    for external_id, rem in deduped.items():
        if external_id not in existing:
            db.add(Reminder(
                workspace_id=workspace_id,
                source_id=source_id,
                external_id=external_id,
                title=rem.title,
                due_at=rem.due_at,
                completed_at=rem.completed_at,
                is_completed=rem.is_completed,
                priority=rem.priority,
                list_name=rem.list_name,
                notes=rem.notes,
                write_through_status="pending",
                created_by=source.registered_by,
            ))
            inserted += 1
        elif _reminder_changed(existing[external_id], rem):
            _apply_reminder(existing[external_id], rem)
            updated += 1
        else:
            unchanged += 1

    source.last_sync_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "reminders_upserted",
        source_id=str(source_id),
        workspace_id=str(workspace_id),
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
    )
    return inserted, updated, unchanged
