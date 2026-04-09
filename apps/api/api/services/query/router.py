"""Deterministic query router: pattern match → parameterized SQL → ResponseEnvelope.

Steps 1-2 of the 5-step query pipeline:
  1. Regex pattern match → QueryIntent (patterns.py)
  2. Parameterized SQL against calendar_events / reminders / contacts → cards

All queries use SQLAlchemy `select()` with bind-params only — never string
concatenation.  Every query filters on workspace_id.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
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

logger = structlog.get_logger()

__all__ = ["classify_query", "route_deterministic"]


# ---------------------------------------------------------------------------
# Calendar range handler
# ---------------------------------------------------------------------------


async def _handle_calendar_range(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    date_ref = params["date_ref"]
    bounds = parse_date_reference(date_ref)
    if bounds is None:
        return []

    start, end = bounds

    stmt = (
        select(CalendarEvent)
        .where(
            and_(
                CalendarEvent.workspace_id == workspace_id,
                CalendarEvent.start_at >= start,
                CalendarEvent.start_at <= end,
            )
        )
        .order_by(CalendarEvent.start_at)
        .limit(50)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    now = datetime.now(timezone.utc)
    cards: list[Card] = []
    for event in events:
        score = _score_calendar_result(event, now)
        payload = {
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
    return cards


def _score_calendar_result(event: CalendarEvent, now: datetime) -> float:
    """Score a calendar event for query results (simpler than Today scoring)."""
    if event.is_all_day:
        return 0.60
    start = event.start_at.replace(tzinfo=timezone.utc) if event.start_at.tzinfo is None else event.start_at
    delta = (start - now).total_seconds() / 3600
    if delta < 0:
        return 0.30  # past
    if delta < 1:
        return 0.90  # imminent
    return max(0.40, 0.80 - delta * 0.02)


# ---------------------------------------------------------------------------
# Reminders range handler
# ---------------------------------------------------------------------------


async def _handle_reminders_range(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    date_ref = params["date_ref"]
    now = datetime.now(timezone.utc)

    # Special case: "overdue" means all incomplete reminders past due
    if date_ref == "overdue":
        stmt = (
            select(Reminder)
            .where(
                and_(
                    Reminder.workspace_id == workspace_id,
                    Reminder.is_completed.is_(False),
                    Reminder.deleted_at.is_(None),
                    Reminder.due_at < now,
                )
            )
            .order_by(Reminder.due_at)
            .limit(50)
        )
    else:
        # Strip leading "due " if present (e.g. "due today" → "today")
        clean_ref = date_ref.removeprefix("due ").strip()
        bounds = parse_date_reference(clean_ref)
        if bounds is None:
            return []
        start, end = bounds

        stmt = (
            select(Reminder)
            .where(
                and_(
                    Reminder.workspace_id == workspace_id,
                    Reminder.is_completed.is_(False),
                    Reminder.deleted_at.is_(None),
                    or_(
                        and_(Reminder.due_at >= start, Reminder.due_at <= end),
                        # Include overdue if querying a range that includes today
                        Reminder.due_at < start,
                    ) if start <= now else and_(
                        Reminder.due_at >= start,
                        Reminder.due_at <= end,
                    ),
                )
            )
            .order_by(Reminder.due_at.nulls_last())
            .limit(50)
        )

    result = await db.execute(stmt)
    reminders = result.scalars().all()

    cards: list[Card] = []
    for reminder in reminders:
        is_overdue = reminder.due_at is not None and (
            reminder.due_at.replace(tzinfo=timezone.utc) if reminder.due_at.tzinfo is None else reminder.due_at
        ) < now
        score = 1.0 if is_overdue else 0.60
        payload = {
            "title": reminder.title,
            "due_at": reminder.due_at.isoformat() if reminder.due_at else None,
            "priority": reminder.priority,
            "list_name": reminder.list_name,
            "notes": reminder.notes,
            "is_overdue": is_overdue,
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
    return cards


# ---------------------------------------------------------------------------
# Contact search handler
# ---------------------------------------------------------------------------


async def _handle_contact_search(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    name = params["name"]
    # Use ILIKE for case-insensitive search — parameterized via bind
    like_pattern = f"%{name}%"

    stmt = (
        select(Contact)
        .where(
            and_(
                Contact.workspace_id == workspace_id,
                Contact.deleted_at.is_(None),
                or_(
                    Contact.display_name.ilike(like_pattern),
                    Contact.first_name.ilike(like_pattern),
                    Contact.last_name.ilike(like_pattern),
                ),
            )
        )
        .order_by(Contact.display_name)
        .limit(20)
    )

    result = await db.execute(stmt)
    contacts = result.scalars().all()
    return [_contact_to_card(c) for c in contacts]


async def _handle_contact_by_org(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    org = params["organization"]
    like_pattern = f"%{org}%"

    stmt = (
        select(Contact)
        .where(
            and_(
                Contact.workspace_id == workspace_id,
                Contact.deleted_at.is_(None),
                Contact.organization.ilike(like_pattern),
            )
        )
        .order_by(Contact.display_name)
        .limit(20)
    )

    result = await db.execute(stmt)
    contacts = result.scalars().all()
    return [_contact_to_card(c) for c in contacts]


def _contact_to_card(contact: Contact) -> PersonCard:
    payload = {
        "display_name": contact.display_name,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "organization": contact.organization,
        "job_title": contact.job_title,
        "emails": contact.emails_json or [],
        "phones": contact.phones_json or [],
    }
    return PersonCard(
        id=contact.id,
        priority_score=0.70,
        source_ids=[contact.source_id],
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Intent → handler dispatch
# ---------------------------------------------------------------------------

_HANDLERS = {
    "calendar_range": _handle_calendar_range,
    "reminders_range": _handle_reminders_range,
    "contact_search": _handle_contact_search,
    "contact_by_org": _handle_contact_by_org,
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

    cards.sort(key=lambda c: c.priority_score, reverse=True)

    return make_envelope(
        cards=cards,
        confidence_level="deterministic",
        query_path="deterministic",
        latency_ms=latency_ms,
    )
