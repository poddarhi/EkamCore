"""Today card assembly: CalendarCardSource + ReminderCardSource + StatusCardSource."""

import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.envelope import Card, ResponseEnvelope, make_envelope
from api.services.today.calendar_card_source import CalendarCardSource
from api.services.today.pack_card_source import PackCardSource
from api.services.today.person_card_source import PersonCardSource
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
    t0 = time.perf_counter()

    now = reference_dt or datetime.now(timezone.utc)
    today = now.date()

    calendar_source = CalendarCardSource(workspace_id=workspace_id, db=db)
    reminder_source = ReminderCardSource(workspace_id=workspace_id, db=db)
    status_source = StatusCardSource(workspace_id=workspace_id)
    person_source = PersonCardSource(workspace_id=workspace_id, db=db)
    pack_source = PackCardSource(workspace_id=workspace_id, db=db)

    event_cards = await calendar_source.fetch(today=today, now=now)
    reminder_cards = await reminder_source.fetch(today=today, now=now)
    status_card = status_source.fetch(now=now)
    person_cards = await person_source.fetch(today=today, now=now)
    pack_cards = await pack_source.fetch(today=today, now=now)

    all_cards: list[Card] = [
        *event_cards,
        *reminder_cards,
        *person_cards,
        *pack_cards,
        status_card,
    ]
    all_cards.sort(key=lambda c: c.priority_score, reverse=True)

    latency_ms = int((time.perf_counter() - t0) * 1000)

    return make_envelope(
        cards=all_cards,
        query_path="deterministic",
        latency_ms=latency_ms,
    )
