"""CalendarCardSource: fetch today's events and produce EventCards with priority scores."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.schemas.envelope import EventCard

logger = structlog.get_logger()

# Thresholds for scoring
_SOON_MINUTES = 30  # "starting soon" window


def _score_event(event: CalendarEvent, now: datetime) -> float:
    """Compute a [0, 1] priority score for a calendar event.

    Scoring rules (higher = more prominent):
    - All-day events: 0.60 (visible but not urgent)
    - Ongoing (already started, not yet ended): 0.95
    - Starting within _SOON_MINUTES: 0.90
    - Future today: 0.70 — (minutes_until_start / 1440) * 0.30
    - Ended today (past): 0.20
    """
    if event.is_all_day:
        return 0.60

    start = _to_utc(event.start_at)
    end = _to_utc(event.end_at) if event.end_at else start + timedelta(hours=1)

    if start <= now <= end:
        return 0.95

    delta_minutes = (start - now).total_seconds() / 60
    if delta_minutes < 0:
        # Already ended
        return 0.20

    if delta_minutes <= _SOON_MINUTES:
        return 0.90

    # Future: scale between 0.70 and 0.40 based on how far away
    # Max future window is 1440 min (24h). Closer = higher score.
    clamped = min(delta_minutes, 1440)
    return round(0.70 - (clamped / 1440) * 0.30, 4)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _day_bounds(today: date) -> tuple[datetime, datetime]:
    """Return UTC start/end of a calendar date (naive treated as UTC)."""
    start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end = datetime.combine(today, time.max, tzinfo=timezone.utc)
    return start, end


class CalendarCardSource:
    def __init__(self, *, workspace_id: UUID, db: AsyncSession) -> None:
        self._workspace_id = workspace_id
        self._db = db

    async def fetch(self, *, today: date, now: datetime) -> list[EventCard]:
        """Return EventCards for all events that overlap with today."""
        day_start, day_end = _day_bounds(today)

        stmt = (
            select(CalendarEvent)
            .where(
                and_(
                    CalendarEvent.workspace_id == self._workspace_id,
                    # Event overlaps today: starts before end of day AND ends after start of day
                    CalendarEvent.start_at <= day_end,
                    # For all-day or events without end, treat end as start+23h59m
                    # We include events whose start_at is within today
                    CalendarEvent.start_at >= day_start,
                )
            )
            .order_by(CalendarEvent.start_at)
        )

        result = await self._db.execute(stmt)
        events = result.scalars().all()

        cards: list[EventCard] = []
        for event in events:
            score = _score_event(event, now)
            payload: dict = {
                "title": event.title,
                "start_at": event.start_at.isoformat(),
                "end_at": event.end_at.isoformat() if event.end_at else None,
                "is_all_day": event.is_all_day,
                "location": event.location,
                "calendar_name": event.calendar_name,
                "participants": event.participants_json or [],
            }
            cards.append(
                EventCard(
                    id=event.id,
                    priority_score=score,
                    source_ids=[event.source_id],
                    payload=payload,
                )
            )

        logger.debug("calendar_cards_fetched", count=len(cards), workspace_id=str(self._workspace_id))
        return cards
