"""Recap generator: assemble daily or weekly recap cards from historical data.

Daily recap: events + completed reminders + newly overdue reminders for a single date.
Weekly recap: same data aggregated over 7 days, grouped by day.

Cards are sorted by date (ascending) then priority_score (descending).
Results are cached in Redis for 1 hour.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.reminder import Reminder
from api.schemas.envelope import (
    CacheHint,
    Card,
    EventCard,
    ReminderCard,
    ResponseEnvelope,
    make_envelope,
)
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

_CACHE_TTL_SECS = 3600  # 1 hour


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    """Return UTC start (00:00:00) and end (23:59:59.999999) for a date."""
    start = datetime.combine(d, dt_time.min, tzinfo=timezone.utc)
    end = datetime.combine(d, dt_time.max, tzinfo=timezone.utc)
    return start, end


def _cache_key(workspace_id: UUID, period: str, target_date: date) -> str:
    return f"recap:{workspace_id}:{period}:{target_date.isoformat()}"


# ---------------------------------------------------------------------------
# Event query
# ---------------------------------------------------------------------------


async def _fetch_events_for_range(
    db: AsyncSession,
    workspace_id: UUID,
    range_start: date,
    range_end: date,
) -> list[EventCard]:
    """Fetch calendar events within [range_start, range_end] (inclusive)."""
    day_start, _ = _day_bounds(range_start)
    _, day_end = _day_bounds(range_end)

    stmt = (
        select(CalendarEvent)
        .where(
            and_(
                CalendarEvent.workspace_id == workspace_id,
                CalendarEvent.start_at >= day_start,
                CalendarEvent.start_at <= day_end,
            )
        )
        .order_by(CalendarEvent.start_at)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    cards: list[EventCard] = []
    for event in events:
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
                priority_score=0.50,  # Recap events have flat priority
                source_ids=[event.source_id],
                payload=payload,
            )
        )
    return cards


# ---------------------------------------------------------------------------
# Completed reminders query
# ---------------------------------------------------------------------------


async def _fetch_completed_reminders(
    db: AsyncSession,
    workspace_id: UUID,
    range_start: date,
    range_end: date,
) -> list[ReminderCard]:
    """Fetch reminders completed within [range_start, range_end]."""
    day_start, _ = _day_bounds(range_start)
    _, day_end = _day_bounds(range_end)

    stmt = (
        select(Reminder)
        .where(
            and_(
                Reminder.workspace_id == workspace_id,
                Reminder.is_completed.is_(True),
                Reminder.deleted_at.is_(None),
                Reminder.completed_at >= day_start,
                Reminder.completed_at <= day_end,
            )
        )
        .order_by(Reminder.completed_at)
    )

    result = await db.execute(stmt)
    reminders = result.scalars().all()

    cards: list[ReminderCard] = []
    for reminder in reminders:
        payload: dict = {
            "title": reminder.title,
            "due_at": reminder.due_at.isoformat() if reminder.due_at else None,
            "priority": reminder.priority,
            "list_name": reminder.list_name,
            "notes": reminder.notes,
            "is_overdue": False,
            "completed_at": reminder.completed_at.isoformat() if reminder.completed_at else None,
        }
        source_ids = [reminder.source_id] if reminder.source_id else []
        cards.append(
            ReminderCard(
                id=reminder.id,
                priority_score=0.40,
                source_ids=source_ids,
                payload=payload,
            )
        )
    return cards


# ---------------------------------------------------------------------------
# Newly overdue reminders query
# ---------------------------------------------------------------------------


async def _fetch_newly_overdue_reminders(
    db: AsyncSession,
    workspace_id: UUID,
    range_start: date,
    range_end: date,
) -> list[ReminderCard]:
    """Fetch reminders that became overdue within the date range.

    A reminder "became overdue" if its due_at falls in the range and it is
    still incomplete.
    """
    day_start, _ = _day_bounds(range_start)
    _, day_end = _day_bounds(range_end)

    stmt = (
        select(Reminder)
        .where(
            and_(
                Reminder.workspace_id == workspace_id,
                Reminder.is_completed.is_(False),
                Reminder.deleted_at.is_(None),
                Reminder.due_at >= day_start,
                Reminder.due_at <= day_end,
            )
        )
        .order_by(Reminder.due_at)
    )

    result = await db.execute(stmt)
    reminders = result.scalars().all()

    cards: list[ReminderCard] = []
    for reminder in reminders:
        payload: dict = {
            "title": reminder.title,
            "due_at": reminder.due_at.isoformat() if reminder.due_at else None,
            "priority": reminder.priority,
            "list_name": reminder.list_name,
            "notes": reminder.notes,
            "is_overdue": True,
        }
        source_ids = [reminder.source_id] if reminder.source_id else []
        cards.append(
            ReminderCard(
                id=reminder.id,
                priority_score=0.80,  # Overdue items are prominent in recap
                source_ids=source_ids,
                payload=payload,
            )
        )
    return cards


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


async def generate_recap(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    period: Literal["daily", "weekly"] = "daily",
    target_date: date | None = None,
) -> ResponseEnvelope:
    """Assemble a recap for the given period and return a ResponseEnvelope.

    Args:
        workspace_id: Workspace to query.
        db: Database session.
        period: "daily" for a single day, "weekly" for 7 days.
        target_date: The date to recap. Defaults to yesterday (UTC).
    """
    t0 = time.perf_counter()

    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    # Check Redis cache
    cache_key = _cache_key(workspace_id, period, target_date)
    r = get_redis(REDIS_DB_CACHE)
    cached = await r.get(cache_key)
    if cached is not None:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.debug("recap_cache_hit", cache_key=cache_key)
        envelope_data = json.loads(cached)
        envelope = ResponseEnvelope.model_validate(envelope_data)
        # Update latency to reflect cache hit
        envelope.metadata.latency_ms = latency_ms
        return envelope

    # Compute date range
    if period == "weekly":
        range_start = target_date - timedelta(days=6)
        range_end = target_date
    else:
        range_start = target_date
        range_end = target_date

    # Fetch all card types
    event_cards = await _fetch_events_for_range(db, workspace_id, range_start, range_end)
    completed_cards = await _fetch_completed_reminders(db, workspace_id, range_start, range_end)
    overdue_cards = await _fetch_newly_overdue_reminders(db, workspace_id, range_start, range_end)

    # Combine and sort: by date (via start_at / due_at in payload) then priority
    all_cards: list[Card] = [*event_cards, *completed_cards, *overdue_cards]
    all_cards.sort(key=lambda c: c.priority_score, reverse=True)

    latency_ms = int((time.perf_counter() - t0) * 1000)

    envelope = make_envelope(
        cards=all_cards,
        query_path="deterministic",
        latency_ms=latency_ms,
        cache_hint=CacheHint(ttl_seconds=_CACHE_TTL_SECS),
    )

    # Store in Redis cache
    try:
        await r.setex(cache_key, _CACHE_TTL_SECS, envelope.model_dump_json())
    except Exception:
        logger.warning("recap_cache_write_failed", cache_key=cache_key, exc_info=True)

    logger.info(
        "recap_generated",
        workspace_id=str(workspace_id),
        period=period,
        target_date=target_date.isoformat(),
        card_count=len(all_cards),
        latency_ms=latency_ms,
    )

    return envelope
