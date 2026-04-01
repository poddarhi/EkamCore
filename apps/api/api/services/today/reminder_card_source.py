"""ReminderCardSource: fetch incomplete reminders due today or overdue, produce ReminderCards."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.reminder import Reminder
from api.schemas.envelope import ReminderCard

logger = structlog.get_logger()

# Priority field values from EventKit / Apple Reminders
_PRIORITY_HIGH = "high"
_PRIORITY_MEDIUM = "medium"


def _score_reminder(reminder: Reminder, now: datetime) -> float:
    """Compute a [0, 1] priority score for a reminder.

    Scoring rules:
    - Overdue (due_at < now): 1.00
    - Due today, priority=high: 0.90
    - Due today, priority=medium: 0.75
    - Due today, priority=low/none: 0.60
    - No due date: 0.30
    """
    if reminder.due_at is None:
        return 0.30

    due = _to_utc(reminder.due_at)
    if due < now:
        return 1.00

    priority = (reminder.priority or "none").lower()
    if priority == _PRIORITY_HIGH:
        return 0.90
    if priority == _PRIORITY_MEDIUM:
        return 0.75
    return 0.60


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ReminderCardSource:
    def __init__(self, *, workspace_id: UUID, db: AsyncSession) -> None:
        self._workspace_id = workspace_id
        self._db = db

    async def fetch(self, *, today: date, now: datetime) -> list[ReminderCard]:
        """Return ReminderCards for incomplete reminders due today or overdue."""
        day_end = datetime.combine(today, time.max, tzinfo=timezone.utc)

        stmt = (
            select(Reminder)
            .where(
                and_(
                    Reminder.workspace_id == self._workspace_id,
                    Reminder.is_completed.is_(False),
                    Reminder.deleted_at.is_(None),
                    # Due today or overdue (or no due date — included separately)
                    or_(
                        Reminder.due_at <= day_end,
                        Reminder.due_at.is_(None),
                    ),
                )
            )
            .order_by(Reminder.due_at.nulls_last(), Reminder.created_at)
        )

        result = await self._db.execute(stmt)
        reminders = result.scalars().all()

        cards: list[ReminderCard] = []
        for reminder in reminders:
            score = _score_reminder(reminder, now)
            payload: dict = {
                "title": reminder.title,
                "due_at": reminder.due_at.isoformat() if reminder.due_at else None,
                "priority": reminder.priority,
                "list_name": reminder.list_name,
                "notes": reminder.notes,
                "is_overdue": reminder.due_at is not None and _to_utc(reminder.due_at) < now,
            }
            source_ids = [reminder.source_id] if reminder.source_id else []
            cards.append(
                ReminderCard(
                    id=reminder.id,
                    priority_score=score,
                    source_ids=source_ids,
                    payload=payload,
                )
            )

        logger.debug("reminder_cards_fetched", count=len(cards), workspace_id=str(self._workspace_id))
        return cards
