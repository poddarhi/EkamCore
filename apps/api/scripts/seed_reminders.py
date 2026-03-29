"""Seed 10 sample reminders: 5 upcoming, 3 overdue, 2 completed.

Finds (or creates) a reminders source on the admin workspace, then upserts
10 synthetic reminders directly via the service layer.

Usage:
    python -m scripts.seed_reminders
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.session import async_session
from api.schemas.reminder import ReminderInput
from api.services.ingestion.reminder_sync import upsert_reminders

ADMIN_EMAIL = "admin@ekamcore.dev"


def _dt(days: int, hours: int = 9) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=hours, minute=0, second=0, microsecond=0)
    return base + timedelta(days=days)


_REMINDERS: list[ReminderInput] = [
    # 5 upcoming
    ReminderInput(
        external_id="seed-rem-upcoming-1",
        title="Schedule annual physical",
        due_at=_dt(1),
        priority="high",
        list_name="Health",
    ),
    ReminderInput(
        external_id="seed-rem-upcoming-2",
        title="Renew car insurance",
        due_at=_dt(3),
        priority="medium",
        list_name="Admin",
    ),
    ReminderInput(
        external_id="seed-rem-upcoming-3",
        title="Buy birthday gift for Alex",
        due_at=_dt(5),
        priority="medium",
        list_name="Personal",
        notes="He likes hiking gear",
    ),
    ReminderInput(
        external_id="seed-rem-upcoming-4",
        title="Submit expense report",
        due_at=_dt(7),
        priority="high",
        list_name="Work",
    ),
    ReminderInput(
        external_id="seed-rem-upcoming-5",
        title="Water the plants",
        due_at=_dt(2),
        priority="low",
        list_name="Home",
    ),
    # 3 overdue (due_at in the past, not completed)
    ReminderInput(
        external_id="seed-rem-overdue-1",
        title="Reply to accountant email",
        due_at=_dt(-2),
        priority="high",
        list_name="Work",
        is_completed=False,
    ),
    ReminderInput(
        external_id="seed-rem-overdue-2",
        title="Call plumber about leak",
        due_at=_dt(-5),
        priority="medium",
        list_name="Home",
        is_completed=False,
    ),
    ReminderInput(
        external_id="seed-rem-overdue-3",
        title="Return library books",
        due_at=_dt(-1),
        priority="low",
        list_name="Personal",
        is_completed=False,
    ),
    # 2 completed
    ReminderInput(
        external_id="seed-rem-completed-1",
        title="Book flight to NYC",
        due_at=_dt(-7),
        completed_at=_dt(-7, hours=14),
        is_completed=True,
        priority="high",
        list_name="Travel",
    ),
    ReminderInput(
        external_id="seed-rem-completed-2",
        title="Pay electricity bill",
        due_at=_dt(-3),
        completed_at=_dt(-3, hours=10),
        is_completed=True,
        priority="medium",
        list_name="Admin",
    ),
]


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

        # Find or create a reminders source
        source = (
            await db.execute(
                select(Source).where(
                    Source.workspace_id == workspace.id,
                    Source.type == "reminders",
                    Source.deleted_at.is_(None),
                )
            )
        ).scalars().first()

        if not source:
            source = Source(
                workspace_id=workspace.id,
                name="Seed Reminders",
                type="reminders",
                registered_by=user.id,
                status="active",
            )
            db.add(source)
            await db.flush()
            print(f"Created reminders source: {source.id}")
        else:
            print(f"Using existing reminders source: {source.id}")

        inserted, updated, unchanged = await upsert_reminders(
            source_id=source.id,
            workspace_id=workspace.id,
            reminders=_REMINDERS,
            db=db,
        )
        await db.commit()

    total = len(_REMINDERS)
    print(f"Seeded {total} reminders: {inserted} inserted, {updated} updated, {unchanged} unchanged.")
    print(f"  Breakdown: 5 upcoming, 3 overdue, 2 completed")


if __name__ == "__main__":
    asyncio.run(seed())
