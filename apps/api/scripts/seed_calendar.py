"""Seed 20 sample calendar events for the next 7 days.

Finds (or creates) a calendar source on the admin workspace, then POSTs
20 synthetic events to the internal ingest endpoint.

Usage:
    python -m scripts.seed_calendar
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.session import async_session
from api.services.ingestion.calendar_sync import upsert_events
from api.schemas.calendar import CalendarEventInput

ADMIN_EMAIL = "admin@ekamcore.dev"

_TITLES = [
    "Team standup",
    "1:1 with manager",
    "Sprint planning",
    "Retrospective",
    "Design review",
    "Architecture sync",
    "Product demo",
    "Code review session",
    "Onboarding call",
    "Customer interview",
    "Lunch with Alex",
    "Doctor appointment",
    "Dentist checkup",
    "Gym session",
    "Evening run",
    "Family dinner",
    "Book club",
    "Quarterly review",
    "Budget planning",
    "Hackathon kickoff",
]

_CALENDARS = ["Work", "Personal", "Health", "Family"]

_PARTICIPANTS = [
    ["alice@example.com", "bob@example.com"],
    ["charlie@example.com"],
    ["diana@example.com", "eric@example.com", "fiona@example.com"],
    [],
]


def _make_event(day_offset: int, slot: int) -> CalendarEventInput:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now + timedelta(days=day_offset, hours=8 + slot * 2)
    end = start + timedelta(hours=1)
    title = _TITLES[day_offset * 3 + slot % len(_TITLES)]
    return CalendarEventInput(
        external_id=f"seed-evt-{day_offset}-{slot}",
        title=title,
        start_at=start,
        end_at=end,
        is_all_day=False,
        location=random.choice([None, "Conference Room A", "Zoom", "Google Meet"]),
        participants_json=random.choice(_PARTICIPANTS) or None,
        recurrence_rule=None,
        calendar_name=random.choice(_CALENDARS),
        notes=None,
    )


async def seed() -> None:
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == ADMIN_EMAIL))).scalar_one_or_none()
        if not user:
            print(f"Admin user {ADMIN_EMAIL} not found. Run seed_admin.py first.")
            return

        workspace = (
            await db.execute(select(Workspace).where(Workspace.owner_id == user.id))
        ).scalars().first()
        if not workspace:
            print("No workspace found for admin.")
            return

        # Find or create a calendar source
        source = (
            await db.execute(
                select(Source).where(
                    Source.workspace_id == workspace.id,
                    Source.type == "calendar",
                    Source.deleted_at.is_(None),
                )
            )
        ).scalars().first()

        if not source:
            source = Source(
                workspace_id=workspace.id,
                name="Seed Calendar",
                type="calendar",
                registered_by=user.id,
                status="active",
            )
            db.add(source)
            await db.flush()
            print(f"Created calendar source: {source.id}")
        else:
            print(f"Using existing calendar source: {source.id}")

        events = [_make_event(day, slot) for day in range(7) for slot in range(3)][:20]

        inserted, updated, unchanged = await upsert_events(
            source_id=source.id,
            workspace_id=workspace.id,
            events=events,
            db=db,
        )
        await db.commit()

    print(f"Seeded {len(events)} events: {inserted} inserted, {updated} updated, {unchanged} unchanged.")


if __name__ == "__main__":
    asyncio.run(seed())
