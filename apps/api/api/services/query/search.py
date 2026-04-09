"""Exact text search across calendar events, reminders, and contacts.

Uses ILIKE for case-insensitive substring matching on title/notes columns.
All queries are parameterized via SQLAlchemy bind-params.

Relevance scoring (simple):
  - Title match: 1.0
  - Notes/location/org match only: 0.7
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.reminder import Reminder
from api.schemas.envelope import Card, EventCard, PersonCard, ReminderCard

logger = structlog.get_logger()

SearchType = Literal["calendar", "reminder", "contact"]


# ---------------------------------------------------------------------------
# Calendar search
# ---------------------------------------------------------------------------


async def search_calendar(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[EventCard]:
    """Search calendar events by title, location, or notes."""
    like = f"%{query}%"

    filters = [
        CalendarEvent.workspace_id == workspace_id,
        or_(
            CalendarEvent.title.ilike(like),
            CalendarEvent.location.ilike(like),
            CalendarEvent.notes.ilike(like),
        ),
    ]
    if date_from is not None:
        filters.append(CalendarEvent.start_at >= date_from)
    if date_to is not None:
        filters.append(CalendarEvent.start_at <= date_to)

    stmt = (
        select(CalendarEvent)
        .where(and_(*filters))
        .order_by(CalendarEvent.start_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    cards: list[EventCard] = []
    for event in events:
        title_match = query.lower() in (event.title or "").lower()
        score = 1.0 if title_match else 0.7
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


async def count_calendar(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> int:
    like = f"%{query}%"
    filters = [
        CalendarEvent.workspace_id == workspace_id,
        or_(
            CalendarEvent.title.ilike(like),
            CalendarEvent.location.ilike(like),
            CalendarEvent.notes.ilike(like),
        ),
    ]
    if date_from is not None:
        filters.append(CalendarEvent.start_at >= date_from)
    if date_to is not None:
        filters.append(CalendarEvent.start_at <= date_to)

    stmt = select(func.count()).select_from(CalendarEvent).where(and_(*filters))
    result = await db.execute(stmt)
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Reminder search
# ---------------------------------------------------------------------------


async def search_reminders(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[ReminderCard]:
    """Search reminders by title or notes."""
    like = f"%{query}%"
    now = datetime.now(timezone.utc)

    stmt = (
        select(Reminder)
        .where(
            and_(
                Reminder.workspace_id == workspace_id,
                Reminder.deleted_at.is_(None),
                or_(
                    Reminder.title.ilike(like),
                    Reminder.notes.ilike(like),
                ),
            )
        )
        .order_by(Reminder.due_at.nulls_last(), Reminder.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    reminders = result.scalars().all()

    cards: list[ReminderCard] = []
    for reminder in reminders:
        title_match = query.lower() in (reminder.title or "").lower()
        score = 1.0 if title_match else 0.7
        is_overdue = reminder.due_at is not None and (
            reminder.due_at.replace(tzinfo=timezone.utc)
            if reminder.due_at.tzinfo is None
            else reminder.due_at
        ) < now
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


async def count_reminders(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
) -> int:
    like = f"%{query}%"
    stmt = (
        select(func.count())
        .select_from(Reminder)
        .where(
            and_(
                Reminder.workspace_id == workspace_id,
                Reminder.deleted_at.is_(None),
                or_(
                    Reminder.title.ilike(like),
                    Reminder.notes.ilike(like),
                ),
            )
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Contact search
# ---------------------------------------------------------------------------


async def search_contacts(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[PersonCard]:
    """Search contacts by name, organization, or job title."""
    like = f"%{query}%"

    stmt = (
        select(Contact)
        .where(
            and_(
                Contact.workspace_id == workspace_id,
                Contact.deleted_at.is_(None),
                or_(
                    Contact.display_name.ilike(like),
                    Contact.first_name.ilike(like),
                    Contact.last_name.ilike(like),
                    Contact.organization.ilike(like),
                    Contact.job_title.ilike(like),
                ),
            )
        )
        .order_by(Contact.display_name)
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    contacts = result.scalars().all()

    cards: list[PersonCard] = []
    for contact in contacts:
        name_match = query.lower() in (contact.display_name or "").lower()
        score = 1.0 if name_match else 0.7
        payload = {
            "display_name": contact.display_name,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "organization": contact.organization,
            "job_title": contact.job_title,
            "emails": contact.emails_json or [],
            "phones": contact.phones_json or [],
        }
        cards.append(
            PersonCard(
                id=contact.id,
                priority_score=score,
                source_ids=[contact.source_id],
                payload=payload,
            )
        )
    return cards


async def count_contacts(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
) -> int:
    like = f"%{query}%"
    stmt = (
        select(func.count())
        .select_from(Contact)
        .where(
            and_(
                Contact.workspace_id == workspace_id,
                Contact.deleted_at.is_(None),
                or_(
                    Contact.display_name.ilike(like),
                    Contact.first_name.ilike(like),
                    Contact.last_name.ilike(like),
                    Contact.organization.ilike(like),
                    Contact.job_title.ilike(like),
                ),
            )
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Multi-type search
# ---------------------------------------------------------------------------


async def search_all(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    types: list[SearchType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Card], dict[str, int]]:
    """Search across multiple types sequentially (single db session).

    Returns (cards sorted by relevance, facet counts by type).
    """
    search_types = types or ["calendar", "reminder", "contact"]

    all_cards: list[Card] = []
    facets: dict[str, int] = {}

    if "calendar" in search_types:
        cards = await search_calendar(
            query, workspace_id, db,
            date_from=date_from, date_to=date_to, limit=limit, offset=offset,
        )
        all_cards.extend(cards)
        facets["calendar"] = await count_calendar(
            query, workspace_id, db, date_from=date_from, date_to=date_to,
        )

    if "reminder" in search_types:
        cards = await search_reminders(query, workspace_id, db, limit=limit, offset=offset)
        all_cards.extend(cards)
        facets["reminder"] = await count_reminders(query, workspace_id, db)

    if "contact" in search_types:
        cards = await search_contacts(query, workspace_id, db, limit=limit, offset=offset)
        all_cards.extend(cards)
        facets["contact"] = await count_contacts(query, workspace_id, db)

    all_cards.sort(key=lambda c: c.priority_score, reverse=True)

    return all_cards, facets
