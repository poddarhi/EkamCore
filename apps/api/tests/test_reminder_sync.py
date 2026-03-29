"""Tests for reminder import service and POST /api/v1/internal/ingest/reminders."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.reminder import Reminder
from api.db.models.source import Source
from api.db.models.workspace import Workspace
from api.errors import NotFoundError, ValidationError
from api.schemas.reminder import ReminderInput
from api.services.ingestion.reminder_sync import upsert_reminders


# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------

def _dt(days: int = 0, hours: int = 9) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=hours, minute=0, second=0, microsecond=0)
    return base + timedelta(days=days)


def _reminder(
    external_id: str = "rem-001",
    title: str = "Buy groceries",
    due_at: datetime | None = None,
    **kwargs,
) -> ReminderInput:
    return ReminderInput(
        external_id=external_id,
        title=title,
        due_at=due_at or _dt(1),
        **kwargs,
    )


async def _make_reminders_source(db: AsyncSession, seed_user: dict) -> Source:
    source = Source(
        workspace_id=seed_user["workspace_id"],
        name="Test Reminders",
        type="reminders",
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(source)
    await db.flush()
    return source


# ---------------------------------------------------------------------------
# Service-level tests (direct function calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_new_reminders(test_session_factory, seed_user: dict) -> None:
    """New reminders are inserted; inserted count is correct."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        inserted, updated, unchanged = await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r1"), _reminder("r2"), _reminder("r3")],
            db=db,
        )
        await db.commit()

    assert inserted == 3
    assert updated == 0
    assert unchanged == 0


@pytest.mark.asyncio
async def test_upsert_updated_reminders(test_session_factory, seed_user: dict) -> None:
    """Re-syncing with a changed title increments the updated counter."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r-upd", title="Old Title")],
            db=db,
        )
        await db.flush()

        inserted, updated, unchanged = await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r-upd", title="New Title")],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Reminder).where(
                    Reminder.source_id == source.id,
                    Reminder.external_id == "r-upd",
                )
            )
        ).scalar_one()
        assert row.title == "New Title"

    assert inserted == 0
    assert updated == 1
    assert unchanged == 0


@pytest.mark.asyncio
async def test_upsert_unchanged_reminders(test_session_factory, seed_user: dict) -> None:
    """Re-syncing identical reminders increments unchanged, not updated."""
    rem = _reminder("r-same", title="Same Title", list_name="Groceries")
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[rem],
            db=db,
        )
        await db.flush()

        inserted, updated, unchanged = await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[rem],
            db=db,
        )

    assert inserted == 0
    assert updated == 0
    assert unchanged == 1


@pytest.mark.asyncio
async def test_upsert_duplicate_external_id_in_request(test_session_factory, seed_user: dict) -> None:
    """Duplicate external_id in the same batch: last occurrence wins, only 1 row created."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        reminders = [
            _reminder("dup", title="First"),
            _reminder("dup", title="Second"),  # should win
        ]
        inserted, updated, unchanged = await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=reminders,
            db=db,
        )
        await db.flush()

        rows = (
            await db.execute(
                select(Reminder).where(
                    Reminder.source_id == source.id,
                    Reminder.external_id == "dup",
                )
            )
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].title == "Second"
    assert inserted == 1
    assert updated == 0


@pytest.mark.asyncio
async def test_upsert_workspace_isolation(test_session_factory, seed_user: dict) -> None:
    """Source from workspace A cannot be used with workspace B's ID."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)
        other_ws = uuid4()

        with pytest.raises(NotFoundError):
            await upsert_reminders(
                source_id=source.id,
                workspace_id=other_ws,  # wrong workspace
                reminders=[_reminder("r1")],
                db=db,
            )


@pytest.mark.asyncio
async def test_upsert_source_not_found(test_session_factory, seed_user: dict) -> None:
    """Non-existent source_id raises NotFoundError."""
    async with test_session_factory() as db:
        with pytest.raises(NotFoundError):
            await upsert_reminders(
                source_id=uuid4(),
                workspace_id=seed_user["workspace_id"],
                reminders=[_reminder("r1")],
                db=db,
            )


@pytest.mark.asyncio
async def test_upsert_wrong_source_type(test_session_factory, seed_user: dict) -> None:
    """Source with type != 'reminders' raises ValidationError."""
    async with test_session_factory() as db:
        non_rem_source = Source(
            workspace_id=seed_user["workspace_id"],
            name="Calendar Source",
            type="calendar",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(non_rem_source)
        await db.flush()

        with pytest.raises(ValidationError) as exc_info:
            await upsert_reminders(
                source_id=non_rem_source.id,
                workspace_id=seed_user["workspace_id"],
                reminders=[_reminder("r1")],
                db=db,
            )
    assert exc_info.value.error_code == "SOURCE_TYPE_MISMATCH"


@pytest.mark.asyncio
async def test_upsert_empty_reminders(test_session_factory, seed_user: dict) -> None:
    """Empty reminder list returns 0/0/0 and still updates last_sync_at."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        inserted, updated, unchanged = await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[],
            db=db,
        )
        await db.flush()

        refreshed = await db.get(Source, source.id)

    assert inserted == 0
    assert updated == 0
    assert unchanged == 0
    assert refreshed is not None
    assert refreshed.last_sync_at is not None


@pytest.mark.asyncio
async def test_last_sync_at_updated(test_session_factory, seed_user: dict) -> None:
    """source.last_sync_at is set after a successful upsert."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)
        assert source.last_sync_at is None

        await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r1")],
            db=db,
        )
        await db.flush()
        await db.refresh(source)

    assert source.last_sync_at is not None


@pytest.mark.asyncio
async def test_completed_reminder_stored(test_session_factory, seed_user: dict) -> None:
    """Completed reminders store completed_at and is_completed=True."""
    completed_at = _dt(-1)
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r-done", is_completed=True, completed_at=completed_at)],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Reminder).where(
                    Reminder.source_id == source.id,
                    Reminder.external_id == "r-done",
                )
            )
        ).scalar_one()

    assert row.is_completed is True
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_overdue_reminder_stored(test_session_factory, seed_user: dict) -> None:
    """Overdue reminders (due_at in the past, not completed) are stored correctly."""
    overdue_due_at = _dt(-3)  # 3 days ago
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r-overdue", due_at=overdue_due_at, is_completed=False)],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Reminder).where(
                    Reminder.source_id == source.id,
                    Reminder.external_id == "r-overdue",
                )
            )
        ).scalar_one()

    assert row.is_completed is False
    assert row.completed_at is None
    assert row.due_at is not None
    assert row.due_at < datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_priority_field_stored(test_session_factory, seed_user: dict) -> None:
    """Priority field is stored and correctly read back."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r-high", priority="high")],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Reminder).where(
                    Reminder.source_id == source.id,
                    Reminder.external_id == "r-high",
                )
            )
        ).scalar_one()

    assert row.priority == "high"


@pytest.mark.asyncio
async def test_completion_update_detected(test_session_factory, seed_user: dict) -> None:
    """Marking a reminder complete on re-sync triggers an update."""
    async with test_session_factory() as db:
        source = await _make_reminders_source(db, seed_user)

        await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r-will-complete", is_completed=False)],
            db=db,
        )
        await db.flush()

        inserted, updated, unchanged = await upsert_reminders(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            reminders=[_reminder("r-will-complete", is_completed=True, completed_at=_dt(0))],
            db=db,
        )

    assert inserted == 0
    assert updated == 1
    assert unchanged == 0


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_reminders_endpoint_success(client: AsyncClient, seed_user: dict, test_session_factory) -> None:
    """POST /api/v1/internal/ingest/reminders returns 200 with counts."""
    async with test_session_factory() as db:
        source = Source(
            workspace_id=seed_user["workspace_id"],
            name="HTTP Test Reminders",
            type="reminders",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(source)
        await db.commit()
        source_id = source.id

    response = await client.post(
        "/api/v1/internal/ingest/reminders",
        json={
            "workspace_id": str(seed_user["workspace_id"]),
            "source_id": str(source_id),
            "reminders": [
                {
                    "external_id": "http-r1",
                    "title": "Call dentist",
                    "due_at": _dt(2).isoformat(),
                    "priority": "medium",
                }
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["inserted"] == 1
    assert data["updated"] == 0
    assert data["unchanged"] == 0


@pytest.mark.asyncio
async def test_ingest_reminders_endpoint_source_not_found(client: AsyncClient, seed_user: dict) -> None:
    """Returns 404 when source_id does not exist."""
    response = await client.post(
        "/api/v1/internal/ingest/reminders",
        json={
            "workspace_id": str(seed_user["workspace_id"]),
            "source_id": str(uuid4()),
            "reminders": [],
        },
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_ingest_reminders_endpoint_workspace_mismatch(
    client: AsyncClient, seed_user: dict, test_session_factory
) -> None:
    """Returns 404 when source_id exists but belongs to a different workspace."""
    async with test_session_factory() as db:
        other_ws = Workspace(name="Other WS", type="personal", owner_id=seed_user["user_id"])
        db.add(other_ws)
        await db.flush()

        source = Source(
            workspace_id=other_ws.id,
            name="Other Reminders",
            type="reminders",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(source)
        await db.commit()
        source_id = source.id

    response = await client.post(
        "/api/v1/internal/ingest/reminders",
        json={
            "workspace_id": str(seed_user["workspace_id"]),  # wrong workspace for this source
            "source_id": str(source_id),
            "reminders": [],
        },
    )
    assert response.status_code == 404
