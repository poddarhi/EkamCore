"""Write-through service: push locally-created reminders to Apple Reminders via manager app.

Architecture:
  1. User creates reminder → inserted with write_through_status='pending'
  2. Background task calls send_to_apple_reminders()
  3. On success: status='success', external_id set
  4. On failure (3 retries): status='failed'

The actual EventKit call is proxied through the Tauri manager app's internal API.
Until the manager app is implemented, the call is stubbed to simulate success.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.reminder import Reminder
from api.db.session import async_session

logger = structlog.get_logger()

_MAX_RETRIES = 3
_RETRY_DELAY_SECS = 2


async def _call_manager_api(reminder: Reminder) -> str:
    """Call the manager app to push a reminder to Apple Reminders.

    Returns the external_id assigned by EventKit.

    Stub: simulates success after a short delay.
    """
    # TODO: Replace with real HTTP call to manager app internal API
    #   POST http://localhost:19876/internal/reminders
    #   Body: {title, due_at, priority, list_name, notes}
    #   Response: {external_id: "x-apple-eventkit://..."}
    await asyncio.sleep(0.1)  # Simulate network latency
    return f"stub-eventkit-{reminder.id.hex[:12]}"


async def send_to_apple_reminders(reminder_id: UUID) -> None:
    """Background task: push a pending reminder to Apple Reminders.

    Uses its own database session (not the request's) since this runs
    after the HTTP response has been sent.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with async_session() as db:
                stmt = select(Reminder).where(Reminder.id == reminder_id)
                result = await db.execute(stmt)
                reminder = result.scalar_one_or_none()

                if reminder is None:
                    logger.error("write_through_reminder_not_found", reminder_id=str(reminder_id))
                    return

                if reminder.write_through_status == "success":
                    logger.debug("write_through_already_done", reminder_id=str(reminder_id))
                    return

                external_id = await _call_manager_api(reminder)

                reminder.write_through_status = "success"
                reminder.external_id = external_id
                await db.commit()

            logger.info(
                "write_through_success",
                reminder_id=str(reminder_id),
                external_id=external_id,
                attempt=attempt,
            )
            return

        except Exception:
            logger.warning(
                "write_through_attempt_failed",
                reminder_id=str(reminder_id),
                attempt=attempt,
                exc_info=True,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAY_SECS * attempt)

    # All retries exhausted — mark as failed
    try:
        async with async_session() as db:
            stmt = select(Reminder).where(Reminder.id == reminder_id)
            result = await db.execute(stmt)
            reminder = result.scalar_one_or_none()
            if reminder:
                reminder.write_through_status = "failed"
                await db.commit()
    except Exception:
        logger.error("write_through_status_update_failed", reminder_id=str(reminder_id), exc_info=True)

    logger.error(
        "write_through_exhausted",
        reminder_id=str(reminder_id),
        max_retries=_MAX_RETRIES,
    )
