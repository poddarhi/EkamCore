"""Deterministic query router: pattern match → parameterized SQL → ResponseEnvelope.

Handles all intent types from patterns.py:
  calendar_range, calendar_with_person, calendar_at_location,
  reminders_range, reminders_by_priority, reminders_by_list,
  contact_search, contact_by_org, contact_field,
  count_query, recent_query

All queries use SQLAlchemy `select()` with bind-params only.
Every query filters on workspace_id.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.reminder import Reminder
from api.schemas.envelope import (
    Card,
    EventCard,
    PersonCard,
    ReminderCard,
    ResponseEnvelope,
    make_envelope,
)
from api.services.query.date_parser import parse_date_reference
from api.services.query.patterns import QueryIntent, classify_query
from api.services.search.photo_search import PhotoFilters, search_photos

logger = structlog.get_logger()

__all__ = ["classify_query", "route_deterministic"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _score_calendar_result(event: CalendarEvent, now: datetime) -> float:
    if event.is_all_day:
        return 0.60
    start = _to_utc(event.start_at)
    delta = (start - now).total_seconds() / 3600
    if delta < 0:
        return 0.30
    if delta < 1:
        return 0.90
    return max(0.40, 0.80 - delta * 0.02)


def _event_to_card(event: CalendarEvent, score: float) -> EventCard:
    return EventCard(
        id=event.id,
        priority_score=score,
        source_ids=[event.source_id],
        payload={
            "title": event.title,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat() if event.end_at else None,
            "is_all_day": event.is_all_day,
            "location": event.location,
            "calendar_name": event.calendar_name,
            "participants": event.participants_json or [],
        },
    )


def _reminder_to_card(reminder: Reminder, now: datetime) -> ReminderCard:
    is_overdue = reminder.due_at is not None and _to_utc(reminder.due_at) < now
    score = 1.0 if is_overdue else 0.60
    return ReminderCard(
        id=reminder.id,
        priority_score=score,
        source_ids=[reminder.source_id] if reminder.source_id else [],
        payload={
            "title": reminder.title,
            "due_at": reminder.due_at.isoformat() if reminder.due_at else None,
            "priority": reminder.priority,
            "list_name": reminder.list_name,
            "notes": reminder.notes,
            "is_overdue": is_overdue,
        },
    )


def _contact_to_card(contact: Contact) -> PersonCard:
    return PersonCard(
        id=contact.id,
        priority_score=0.70,
        source_ids=[contact.source_id],
        payload={
            "display_name": contact.display_name,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "organization": contact.organization,
            "job_title": contact.job_title,
            "emails": contact.emails_json or [],
            "phones": contact.phones_json or [],
            "birthday": contact.birthday.isoformat() if contact.birthday else None,
        },
    )


# ---------------------------------------------------------------------------
# Calendar handlers
# ---------------------------------------------------------------------------


async def _handle_calendar_range(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    bounds = parse_date_reference(params["date_ref"])
    if bounds is None:
        return []
    start, end = bounds
    now = datetime.now(timezone.utc)

    stmt = (
        select(CalendarEvent)
        .where(and_(
            CalendarEvent.workspace_id == workspace_id,
            CalendarEvent.start_at >= start,
            CalendarEvent.start_at <= end,
        ))
        .order_by(CalendarEvent.start_at)
        .limit(50)
    )
    result = await db.execute(stmt)
    return [_event_to_card(e, _score_calendar_result(e, now)) for e in result.scalars().all()]


async def _handle_calendar_with_person(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    person = params["person"]
    bounds = parse_date_reference(params.get("date_ref", "this week"))
    if bounds is None:
        return []
    start, end = bounds
    now = datetime.now(timezone.utc)
    like = f"%{person}%"

    stmt = (
        select(CalendarEvent)
        .where(and_(
            CalendarEvent.workspace_id == workspace_id,
            CalendarEvent.start_at >= start,
            CalendarEvent.start_at <= end,
            # Check participants_json (JSONB) contains person name
            # Using cast to text + ILIKE as a portable approach
            func.cast(CalendarEvent.participants_json, func.text()).ilike(like),
        ))
        .order_by(CalendarEvent.start_at)
        .limit(50)
    )
    result = await db.execute(stmt)
    return [_event_to_card(e, _score_calendar_result(e, now)) for e in result.scalars().all()]


async def _handle_calendar_at_location(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    location = params["location"]
    like = f"%{location}%"
    now = datetime.now(timezone.utc)

    stmt = (
        select(CalendarEvent)
        .where(and_(
            CalendarEvent.workspace_id == workspace_id,
            CalendarEvent.location.ilike(like),
        ))
        .order_by(CalendarEvent.start_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return [_event_to_card(e, _score_calendar_result(e, now)) for e in result.scalars().all()]


# ---------------------------------------------------------------------------
# Reminder handlers
# ---------------------------------------------------------------------------


async def _handle_reminders_range(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    date_ref = params["date_ref"]
    now = datetime.now(timezone.utc)

    if date_ref == "overdue":
        stmt = (
            select(Reminder)
            .where(and_(
                Reminder.workspace_id == workspace_id,
                Reminder.is_completed.is_(False),
                Reminder.deleted_at.is_(None),
                Reminder.due_at < now,
            ))
            .order_by(Reminder.due_at)
            .limit(50)
        )
    else:
        clean_ref = date_ref.removeprefix("due ").strip()
        bounds = parse_date_reference(clean_ref)
        if bounds is None:
            return []
        start, end = bounds

        if start <= now:
            # Include overdue when range includes past
            stmt = (
                select(Reminder)
                .where(and_(
                    Reminder.workspace_id == workspace_id,
                    Reminder.is_completed.is_(False),
                    Reminder.deleted_at.is_(None),
                    or_(
                        and_(Reminder.due_at >= start, Reminder.due_at <= end),
                        Reminder.due_at < start,
                    ),
                ))
                .order_by(Reminder.due_at.nulls_last())
                .limit(50)
            )
        else:
            stmt = (
                select(Reminder)
                .where(and_(
                    Reminder.workspace_id == workspace_id,
                    Reminder.is_completed.is_(False),
                    Reminder.deleted_at.is_(None),
                    Reminder.due_at >= start,
                    Reminder.due_at <= end,
                ))
                .order_by(Reminder.due_at.nulls_last())
                .limit(50)
            )

    result = await db.execute(stmt)
    return [_reminder_to_card(r, now) for r in result.scalars().all()]


async def _handle_reminders_by_priority(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    priority = params["priority"]
    now = datetime.now(timezone.utc)

    stmt = (
        select(Reminder)
        .where(and_(
            Reminder.workspace_id == workspace_id,
            Reminder.is_completed.is_(False),
            Reminder.deleted_at.is_(None),
            Reminder.priority == priority,
        ))
        .order_by(Reminder.due_at.nulls_last())
        .limit(50)
    )
    result = await db.execute(stmt)
    return [_reminder_to_card(r, now) for r in result.scalars().all()]


async def _handle_reminders_by_list(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    list_name = params["list_name"]
    like = f"%{list_name}%"
    now = datetime.now(timezone.utc)

    stmt = (
        select(Reminder)
        .where(and_(
            Reminder.workspace_id == workspace_id,
            Reminder.is_completed.is_(False),
            Reminder.deleted_at.is_(None),
            Reminder.list_name.ilike(like),
        ))
        .order_by(Reminder.due_at.nulls_last())
        .limit(50)
    )
    result = await db.execute(stmt)
    return [_reminder_to_card(r, now) for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# Contact handlers
# ---------------------------------------------------------------------------


async def _handle_contact_search(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    name = params["name"]
    like = f"%{name}%"

    stmt = (
        select(Contact)
        .where(and_(
            Contact.workspace_id == workspace_id,
            Contact.deleted_at.is_(None),
            or_(
                Contact.display_name.ilike(like),
                Contact.first_name.ilike(like),
                Contact.last_name.ilike(like),
            ),
        ))
        .order_by(Contact.display_name)
        .limit(20)
    )
    result = await db.execute(stmt)
    return [_contact_to_card(c) for c in result.scalars().all()]


async def _handle_contact_by_org(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    org = params["organization"]
    like = f"%{org}%"

    stmt = (
        select(Contact)
        .where(and_(
            Contact.workspace_id == workspace_id,
            Contact.deleted_at.is_(None),
            Contact.organization.ilike(like),
        ))
        .order_by(Contact.display_name)
        .limit(20)
    )
    result = await db.execute(stmt)
    return [_contact_to_card(c) for c in result.scalars().all()]


async def _handle_contact_field(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    """Look up a specific contact field (phone, email, birthday)."""
    name = params["name"]
    like = f"%{name}%"

    stmt = (
        select(Contact)
        .where(and_(
            Contact.workspace_id == workspace_id,
            Contact.deleted_at.is_(None),
            or_(
                Contact.display_name.ilike(like),
                Contact.first_name.ilike(like),
                Contact.last_name.ilike(like),
            ),
        ))
        .order_by(Contact.display_name)
        .limit(5)
    )
    result = await db.execute(stmt)
    return [_contact_to_card(c) for c in result.scalars().all()]


# ---------------------------------------------------------------------------
# Stats handler
# ---------------------------------------------------------------------------


async def _handle_count_query(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    """Return a count as answer_text — no cards, just metadata."""
    entity = params["entity"].rstrip("s")  # normalize plural
    date_ref = params.get("date_ref", "today")
    bounds = parse_date_reference(date_ref)

    if entity in ("event", "meeting", "appointment"):
        if bounds:
            start, end = bounds
            stmt = (
                select(func.count())
                .select_from(CalendarEvent)
                .where(and_(
                    CalendarEvent.workspace_id == workspace_id,
                    CalendarEvent.start_at >= start,
                    CalendarEvent.start_at <= end,
                ))
            )
        else:
            stmt = (
                select(func.count())
                .select_from(CalendarEvent)
                .where(CalendarEvent.workspace_id == workspace_id)
            )
    elif entity in ("reminder", "task", "todo"):
        stmt = (
            select(func.count())
            .select_from(Reminder)
            .where(and_(
                Reminder.workspace_id == workspace_id,
                Reminder.is_completed.is_(False),
                Reminder.deleted_at.is_(None),
            ))
        )
    elif entity == "contact":
        stmt = (
            select(func.count())
            .select_from(Contact)
            .where(and_(
                Contact.workspace_id == workspace_id,
                Contact.deleted_at.is_(None),
            ))
        )
    else:
        return []

    result = await db.execute(stmt)
    count = result.scalar_one()
    # Store count in a special way — the envelope's answer_text will carry it
    return [("__count__", count, entity, date_ref)]  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Recent handler
# ---------------------------------------------------------------------------


async def _handle_recent_query(
    params: dict[str, str], workspace_id: UUID, db: AsyncSession,
) -> list[Card]:
    entity = params["entity"].rstrip("s")
    now = datetime.now(timezone.utc)

    if entity in ("event", "meeting"):
        stmt = (
            select(CalendarEvent)
            .where(CalendarEvent.workspace_id == workspace_id)
            .order_by(CalendarEvent.start_at.desc())
            .limit(10)
        )
        result = await db.execute(stmt)
        return [_event_to_card(e, _score_calendar_result(e, now)) for e in result.scalars().all()]

    if entity in ("reminder", "task", "todo"):
        stmt = (
            select(Reminder)
            .where(and_(
                Reminder.workspace_id == workspace_id,
                Reminder.deleted_at.is_(None),
            ))
            .order_by(Reminder.created_at.desc())
            .limit(10)
        )
        result = await db.execute(stmt)
        return [_reminder_to_card(r, now) for r in result.scalars().all()]

    if entity == "contact":
        stmt = (
            select(Contact)
            .where(and_(
                Contact.workspace_id == workspace_id,
                Contact.deleted_at.is_(None),
            ))
            .order_by(Contact.created_at.desc())
            .limit(10)
        )
        result = await db.execute(stmt)
        return [_contact_to_card(c) for c in result.scalars().all()]

    return []


# ---------------------------------------------------------------------------
# Photo handlers
# ---------------------------------------------------------------------------


async def _handle_photo_date(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    date_ref = params.get("date_ref", "today")
    bounds = parse_date_reference(date_ref)
    date_from = bounds[0] if bounds else None
    date_to = bounds[1] if bounds else None

    cards, _ = await search_photos(
        workspace_ids=[workspace_id],
        query="",
        filters=PhotoFilters(date_from=date_from, date_to=date_to),
        limit=20,
        offset=0,
        db=db,
    )
    return cards


async def _handle_photo_location(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    location = params.get("location", "")
    cards, _ = await search_photos(
        workspace_ids=[workspace_id],
        query="",
        filters=PhotoFilters(location_contains=location),
        limit=20,
        offset=0,
        db=db,
    )
    return cards


async def _handle_photo_camera(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    camera = params.get("camera", "")
    cards, _ = await search_photos(
        workspace_ids=[workspace_id],
        query="",
        filters=PhotoFilters(camera=camera),
        limit=20,
        offset=0,
        db=db,
    )
    return cards


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_HANDLERS = {
    "calendar_range": _handle_calendar_range,
    "calendar_with_person": _handle_calendar_with_person,
    "calendar_at_location": _handle_calendar_at_location,
    "reminders_range": _handle_reminders_range,
    "reminders_by_priority": _handle_reminders_by_priority,
    "reminders_by_list": _handle_reminders_by_list,
    "contact_search": _handle_contact_search,
    "contact_by_org": _handle_contact_by_org,
    "contact_field": _handle_contact_field,
    "count_query": _handle_count_query,
    "recent_query": _handle_recent_query,
    "photo_date": _handle_photo_date,
    "photo_location": _handle_photo_location,
    "photo_camera": _handle_photo_camera,
}


async def route_deterministic(
    intent: QueryIntent,
    workspace_id: UUID,
    db: AsyncSession,
) -> ResponseEnvelope:
    """Execute the deterministic handler for *intent* and return a ResponseEnvelope."""
    t0 = time.perf_counter()

    handler = _HANDLERS.get(intent.intent_type)
    if handler is None:
        logger.warning("query_no_handler", intent_type=intent.intent_type)
        return make_envelope(
            answer_text="I don't understand that query yet.",
            query_path="deterministic",
            latency_ms=0,
        )

    cards = await handler(intent.params, workspace_id, db)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # Special handling for count queries
    if cards and isinstance(cards[0], tuple) and cards[0][0] == "__count__":
        _, count, entity, date_ref = cards[0]
        return make_envelope(
            answer_text=f"You have {count} {entity}{'s' if count != 1 else ''} {date_ref}.",
            confidence_level="deterministic",
            query_path="deterministic",
            latency_ms=latency_ms,
        )

    cards.sort(key=lambda c: c.priority_score, reverse=True)

    return make_envelope(
        cards=cards,
        confidence_level="deterministic",
        query_path="deterministic",
        latency_ms=latency_ms,
    )
