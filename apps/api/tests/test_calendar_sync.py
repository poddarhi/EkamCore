"""Tests for calendar event import service and POST /api/v1/internal/ingest/calendar."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.source import Source
from api.db.models.workspace import Workspace
from api.errors import NotFoundError, ValidationError
from api.schemas.calendar import CalendarEventInput
from api.services.ingestion.calendar_sync import upsert_events


# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------

def _dt(days: int = 0, hours: int = 9) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=hours, minute=0, second=0, microsecond=0)
    return base + timedelta(days=days)


def _event(
    external_id: str = "evt-001",
    title: str = "Team standup",
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    **kwargs,
) -> CalendarEventInput:
    return CalendarEventInput(
        external_id=external_id,
        title=title,
        start_at=start_at or _dt(0),
        end_at=end_at or _dt(0, 10),
        **kwargs,
    )


async def _make_calendar_source(db: AsyncSession, seed_user: dict) -> Source:
    source = Source(
        workspace_id=seed_user["workspace_id"],
        name="Test Calendar",
        type="calendar",
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
async def test_upsert_new_events(test_session_factory, seed_user: dict) -> None:
    """New events are inserted; inserted count is correct."""
    async with test_session_factory() as db:
        source = await _make_calendar_source(db, seed_user)

        inserted, updated, unchanged = await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=[_event("e1"), _event("e2"), _event("e3")],
            db=db,
        )
        await db.commit()

    assert inserted == 3
    assert updated == 0
    assert unchanged == 0


@pytest.mark.asyncio
async def test_upsert_updated_events(test_session_factory, seed_user: dict) -> None:
    """Re-syncing with a changed title increments the updated counter."""
    async with test_session_factory() as db:
        source = await _make_calendar_source(db, seed_user)

        await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=[_event("e-upd", title="Old Title")],
            db=db,
        )
        await db.flush()

        inserted, updated, unchanged = await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=[_event("e-upd", title="New Title")],
            db=db,
        )
        await db.flush()

        # Verify the row was mutated
        row = (
            await db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.source_id == source.id,
                    CalendarEvent.external_id == "e-upd",
                )
            )
        ).scalar_one()
        assert row.title == "New Title"

    assert inserted == 0
    assert updated == 1
    assert unchanged == 0


@pytest.mark.asyncio
async def test_upsert_unchanged_events(test_session_factory, seed_user: dict) -> None:
    """Re-syncing identical events increments unchanged, not updated."""
    ev = _event("e-same", title="Same Title", location="Office")
    async with test_session_factory() as db:
        source = await _make_calendar_source(db, seed_user)

        await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=[ev],
            db=db,
        )
        await db.flush()

        inserted, updated, unchanged = await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=[ev],
            db=db,
        )

    assert inserted == 0
    assert updated == 0
    assert unchanged == 1


@pytest.mark.asyncio
async def test_upsert_duplicate_external_id_in_request(test_session_factory, seed_user: dict) -> None:
    """Duplicate external_id in the same batch: last occurrence wins, only 1 row created."""
    async with test_session_factory() as db:
        source = await _make_calendar_source(db, seed_user)

        events = [
            _event("dup", title="First"),
            _event("dup", title="Second"),  # should win
        ]
        inserted, updated, unchanged = await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=events,
            db=db,
        )
        await db.flush()

        rows = (
            await db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.source_id == source.id,
                    CalendarEvent.external_id == "dup",
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
        source = await _make_calendar_source(db, seed_user)
        other_ws = uuid4()

        with pytest.raises(NotFoundError):
            await upsert_events(
                source_id=source.id,
                workspace_id=other_ws,  # wrong workspace
                events=[_event("e1")],
                db=db,
            )


@pytest.mark.asyncio
async def test_upsert_source_not_found(test_session_factory, seed_user: dict) -> None:
    """Non-existent source_id raises NotFoundError."""
    async with test_session_factory() as db:
        with pytest.raises(NotFoundError):
            await upsert_events(
                source_id=uuid4(),
                workspace_id=seed_user["workspace_id"],
                events=[_event("e1")],
                db=db,
            )


@pytest.mark.asyncio
async def test_upsert_wrong_source_type(test_session_factory, seed_user: dict) -> None:
    """Source with type != 'calendar' raises ValidationError."""
    async with test_session_factory() as db:
        non_cal_source = Source(
            workspace_id=seed_user["workspace_id"],
            name="Contacts Source",
            type="contacts",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(non_cal_source)
        await db.flush()

        with pytest.raises(ValidationError) as exc_info:
            await upsert_events(
                source_id=non_cal_source.id,
                workspace_id=seed_user["workspace_id"],
                events=[_event("e1")],
                db=db,
            )
    assert exc_info.value.error_code == "SOURCE_TYPE_MISMATCH"


@pytest.mark.asyncio
async def test_upsert_empty_events(test_session_factory, seed_user: dict) -> None:
    """Empty event list returns 0/0/0 and still updates last_sync_at."""
    async with test_session_factory() as db:
        source = await _make_calendar_source(db, seed_user)

        inserted, updated, unchanged = await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=[],
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
        source = await _make_calendar_source(db, seed_user)
        assert source.last_sync_at is None

        await upsert_events(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            events=[_event("e1")],
            db=db,
        )
        await db.flush()
        await db.refresh(source)

    assert source.last_sync_at is not None


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_calendar_endpoint_success(client: AsyncClient, seed_user: dict, test_session_factory) -> None:
    """POST /api/v1/internal/ingest/calendar returns 200 with counts."""
    async with test_session_factory() as db:
        source = Source(
            workspace_id=seed_user["workspace_id"],
            name="HTTP Test Calendar",
            type="calendar",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(source)
        await db.commit()
        source_id = source.id

    response = await client.post(
        "/api/v1/internal/ingest/calendar",
        json={
            "workspace_id": str(seed_user["workspace_id"]),
            "source_id": str(source_id),
            "events": [
                {
                    "external_id": "http-e1",
                    "title": "Meeting",
                    "start_at": _dt(1).isoformat(),
                    "end_at": _dt(1, 10).isoformat(),
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
async def test_ingest_calendar_endpoint_source_not_found(client: AsyncClient, seed_user: dict) -> None:
    """Returns 404 when source_id does not exist."""
    response = await client.post(
        "/api/v1/internal/ingest/calendar",
        json={
            "workspace_id": str(seed_user["workspace_id"]),
            "source_id": str(uuid4()),
            "events": [],
        },
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_ingest_calendar_endpoint_workspace_mismatch(
    client: AsyncClient, seed_user: dict, test_session_factory
) -> None:
    """Returns 404 when source_id exists but belongs to a different workspace."""
    async with test_session_factory() as db:
        other_ws = Workspace(name="Other WS", type="personal", owner_id=seed_user["user_id"])
        db.add(other_ws)
        await db.flush()

        source = Source(
            workspace_id=other_ws.id,
            name="Other Calendar",
            type="calendar",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(source)
        await db.commit()
        source_id = source.id

    response = await client.post(
        "/api/v1/internal/ingest/calendar",
        json={
            "workspace_id": str(seed_user["workspace_id"]),  # wrong workspace for this source
            "source_id": str(source_id),
            "events": [],
        },
    )
    assert response.status_code == 404
