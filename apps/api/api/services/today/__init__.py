"""Today card assembly: CalendarCardSource + ReminderCardSource + StatusCardSource."""

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.envelope import Card, ResponseEnvelope, make_envelope
from api.services.today.calendar_card_source import CalendarCardSource
from api.services.today.reminder_card_source import ReminderCardSource
from api.services.today.status_card_source import StatusCardSource


async def assemble_today(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    reference_dt: datetime | None = None,
) -> ResponseEnvelope:
    """Assemble all today cards from all sources and return a ResponseEnvelope.

    Args:
        workspace_id: The workspace to query.
        db: Database session.
        reference_dt: Override "now" (UTC). Defaults to datetime.now(UTC).
    """
    now = reference_dt or datetime.now(timezone.utc)
    today = now.date()

    calendar_source = CalendarCardSource(workspace_id=workspace_id, db=db)
    reminder_source = ReminderCardSource(workspace_id=workspace_id, db=db)
    status_source = StatusCardSource(workspace_id=workspace_id)

    event_cards = await calendar_source.fetch(today=today, now=now)
    reminder_cards = await reminder_source.fetch(today=today, now=now)
    status_card = status_source.fetch(now=now)

    all_cards: list[Card] = [*event_cards, *reminder_cards, status_card]
    all_cards.sort(key=lambda c: c.priority_score, reverse=True)

    return make_envelope(
        cards=all_cards,
        query_path="deterministic",
    )
