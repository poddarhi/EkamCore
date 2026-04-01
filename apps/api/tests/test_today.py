"""Tests for S03-003: Today card assembly — CalendarCardSource, ReminderCardSource, StatusCardSource."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.reminder import Reminder
from api.db.models.source import Source
from api.schemas.envelope import ResponseEnvelope
from api.services.today.calendar_card_source import CalendarCardSource, _score_event
from api.services.today.reminder_card_source import ReminderCardSource, _score_reminder
from api.services.today.status_card_source import StatusCardSource

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)  # Wednesday 10:00 UTC
TODAY = NOW.date()


async def _make_calendar_source(db: AsyncSession, seed_user: dict) -> Source:
    src = Source(
        workspace_id=seed_user["workspace_id"],
        name="Test Calendar",
        type="calendar",
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(src)
    await db.flush()
    return src


# ---------------------------------------------------------------------------
# Unit tests: _score_event
# ---------------------------------------------------------------------------


def _make_event(
    *,
    start_offset_min: int = 60,
    duration_min: int = 60,
    is_all_day: bool = False,
) -> SimpleNamespace:
    start = NOW + timedelta(minutes=start_offset_min)
    end = start + timedelta(minutes=duration_min)
    return SimpleNamespace(start_at=start, end_at=end, is_all_day=is_all_day)


class TestScoreEvent:
    def test_all_day_returns_060(self):
        ev = _make_event(is_all_day=True)
        assert _score_event(ev, NOW) == 0.60

    def test_ongoing_returns_095(self):
        ev = _make_event(start_offset_min=-10, duration_min=30)
        assert _score_event(ev, NOW) == 0.95

    def test_starting_soon_returns_090(self):
        ev = _make_event(start_offset_min=15)
        assert _score_event(ev, NOW) == 0.90

    def test_past_event_returns_020(self):
        ev = _make_event(start_offset_min=-120, duration_min=30)
        assert _score_event(ev, NOW) == 0.20

    def test_future_event_score_decreases_with_distance(self):
        near = _make_event(start_offset_min=60)
        far = _make_event(start_offset_min=300)
        assert _score_event(near, NOW) > _score_event(far, NOW)

    def test_future_score_bounded_above_040(self):
        far = _make_event(start_offset_min=1440)
        score = _score_event(far, NOW)
        assert score >= 0.40


# ---------------------------------------------------------------------------
# Unit tests: _score_reminder
# ---------------------------------------------------------------------------


def _make_reminder(
    *,
    due_offset_min: int | None = 60,
    priority: str = "none",
) -> SimpleNamespace:
    due = (NOW + timedelta(minutes=due_offset_min)) if due_offset_min is not None else None
    return SimpleNamespace(due_at=due, priority=priority)


class TestScoreReminder:
    def test_overdue_returns_100(self):
        r = _make_reminder(due_offset_min=-30)
        assert _score_reminder(r, NOW) == 1.00

    def test_no_due_date_returns_030(self):
        r = _make_reminder(due_offset_min=None)
        assert _score_reminder(r, NOW) == 0.30

    def test_high_priority_returns_090(self):
        r = _make_reminder(due_offset_min=60, priority="high")
        assert _score_reminder(r, NOW) == 0.90

    def test_medium_priority_returns_075(self):
        r = _make_reminder(due_offset_min=60, priority="medium")
        assert _score_reminder(r, NOW) == 0.75

    def test_low_priority_returns_060(self):
        r = _make_reminder(due_offset_min=60, priority="low")
        assert _score_reminder(r, NOW) == 0.60

    def test_none_priority_returns_060(self):
        r = _make_reminder(due_offset_min=60, priority="none")
        assert _score_reminder(r, NOW) == 0.60


# ---------------------------------------------------------------------------
# Unit tests: StatusCardSource
# ---------------------------------------------------------------------------


class TestStatusCardSource:
    def _source(self) -> StatusCardSource:
        return StatusCardSource(workspace_id=uuid4())

    def test_morning(self):
        dt = datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc)
        card = self._source().fetch(now=dt)
        assert card.payload["time_of_day"] == "morning"

    def test_afternoon(self):
        dt = datetime(2026, 4, 1, 14, 0, 0, tzinfo=timezone.utc)
        card = self._source().fetch(now=dt)
        assert card.payload["time_of_day"] == "afternoon"

    def test_evening(self):
        dt = datetime(2026, 4, 1, 19, 0, 0, tzinfo=timezone.utc)
        card = self._source().fetch(now=dt)
        assert card.payload["time_of_day"] == "evening"

    def test_night(self):
        dt = datetime(2026, 4, 1, 22, 0, 0, tzinfo=timezone.utc)
        card = self._source().fetch(now=dt)
        assert card.payload["time_of_day"] == "night"

    def test_payload_contains_date_and_weekday(self):
        card = self._source().fetch(now=NOW)
        assert card.payload["date"] == "2026-04-01"
        assert card.payload["weekday"] == "Wednesday"

    def test_priority_score(self):
        card = self._source().fetch(now=NOW)
        assert card.priority_score == 0.50

    def test_type_is_status(self):
        card = self._source().fetch(now=NOW)
        assert card.type == "status"


# ---------------------------------------------------------------------------
# Integration tests: CalendarCardSource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_source_returns_today_events(
    test_session_factory, seed_user: dict
):
    async with test_session_factory() as db:
        src = await _make_calendar_source(db, seed_user)
        ws_id = seed_user["workspace_id"]

        today_event = CalendarEvent(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ev-today-{uuid4().hex[:6]}",
            title="Team standup",
            start_at=NOW + timedelta(hours=1),
            end_at=NOW + timedelta(hours=2),
            is_all_day=False,
        )
        tomorrow_event = CalendarEvent(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ev-tomorrow-{uuid4().hex[:6]}",
            title="Future meeting",
            start_at=NOW + timedelta(days=1),
            end_at=NOW + timedelta(days=1, hours=1),
            is_all_day=False,
        )
        db.add_all([today_event, tomorrow_event])
        await db.flush()

        source = CalendarCardSource(workspace_id=ws_id, db=db)
        cards = await source.fetch(today=TODAY, now=NOW)
        await db.rollback()

    titles = [c.payload["title"] for c in cards]
    assert "Team standup" in titles
    assert "Future meeting" not in titles


@pytest.mark.asyncio
async def test_calendar_source_excludes_other_workspace(
    test_session_factory, seed_user: dict
):
    """Events in workspace B must not appear when querying workspace A."""
    from api.db.models.workspace import Workspace
    from api.db.models.workspace_member import WorkspaceMember
    from api.db.models.user import User
    from api.services.auth import hash_password

    async with test_session_factory() as db:
        # Create a second user+workspace
        other_user = User(
            email=f"other-{uuid4().hex[:8]}@ekamcore.dev",
            display_name="Other",
            password_hash=hash_password("pw"),
            role="standard",
            is_active=True,
        )
        db.add(other_user)
        await db.flush()
        other_ws = Workspace(name="Other WS", type="personal", owner_id=other_user.id)
        db.add(other_ws)
        await db.flush()
        other_member = WorkspaceMember(workspace_id=other_ws.id, user_id=other_user.id, role="admin")
        db.add(other_member)
        await db.flush()

        other_src = Source(
            workspace_id=other_ws.id,
            name="Other Cal",
            type="calendar",
            registered_by=other_user.id,
            status="active",
        )
        db.add(other_src)
        await db.flush()

        event = CalendarEvent(
            workspace_id=other_ws.id,
            source_id=other_src.id,
            external_id=f"ev-other-{uuid4().hex[:6]}",
            title="Other WS event",
            start_at=NOW + timedelta(hours=1),
            end_at=NOW + timedelta(hours=2),
            is_all_day=False,
        )
        db.add(event)
        await db.flush()

        source = CalendarCardSource(workspace_id=seed_user["workspace_id"], db=db)
        cards = await source.fetch(today=TODAY, now=NOW)
        await db.rollback()

    titles = [c.payload["title"] for c in cards]
    assert "Other WS event" not in titles


# ---------------------------------------------------------------------------
# Integration tests: ReminderCardSource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reminder_source_returns_due_today_and_overdue(
    test_session_factory, seed_user: dict
):
    ws_id = seed_user["workspace_id"]
    user_id = seed_user["user_id"]

    async with test_session_factory() as db:
        overdue = Reminder(
            workspace_id=ws_id,
            title=f"Overdue task {uuid4().hex[:6]}",
            due_at=NOW - timedelta(hours=2),
            is_completed=False,
            priority="none",
            created_by=user_id,
        )
        due_today = Reminder(
            workspace_id=ws_id,
            title=f"Due today {uuid4().hex[:6]}",
            due_at=NOW + timedelta(hours=3),
            is_completed=False,
            priority="high",
            created_by=user_id,
        )
        completed = Reminder(
            workspace_id=ws_id,
            title=f"Already done {uuid4().hex[:6]}",
            due_at=NOW + timedelta(hours=1),
            is_completed=True,
            priority="none",
            created_by=user_id,
        )
        future = Reminder(
            workspace_id=ws_id,
            title=f"Due tomorrow {uuid4().hex[:6]}",
            due_at=NOW + timedelta(days=1, hours=1),
            is_completed=False,
            priority="none",
            created_by=user_id,
        )
        db.add_all([overdue, due_today, completed, future])
        await db.flush()

        source = ReminderCardSource(workspace_id=ws_id, db=db)
        cards = await source.fetch(today=TODAY, now=NOW)

        overdue_title = overdue.title
        due_today_title = due_today.title
        completed_title = completed.title
        future_title = future.title
        await db.rollback()

    titles = {c.payload["title"] for c in cards}
    assert overdue_title in titles
    assert due_today_title in titles
    assert completed_title not in titles
    assert future_title not in titles


@pytest.mark.asyncio
async def test_reminder_overdue_flag_in_payload(test_session_factory, seed_user: dict):
    ws_id = seed_user["workspace_id"]
    user_id = seed_user["user_id"]

    async with test_session_factory() as db:
        overdue = Reminder(
            workspace_id=ws_id,
            title=f"Late task {uuid4().hex[:6]}",
            due_at=NOW - timedelta(hours=1),
            is_completed=False,
            priority="none",
            created_by=user_id,
        )
        db.add(overdue)
        await db.flush()

        source = ReminderCardSource(workspace_id=ws_id, db=db)
        cards = await source.fetch(today=TODAY, now=NOW)
        late_title = overdue.title
        await db.rollback()

    overdue_cards = [c for c in cards if c.payload["title"] == late_title]
    assert overdue_cards, "Overdue card not found"
    assert overdue_cards[0].payload["is_overdue"] is True


@pytest.mark.asyncio
async def test_reminder_no_due_date_included(test_session_factory, seed_user: dict):
    ws_id = seed_user["workspace_id"]
    user_id = seed_user["user_id"]

    async with test_session_factory() as db:
        no_due = Reminder(
            workspace_id=ws_id,
            title=f"No deadline {uuid4().hex[:6]}",
            due_at=None,
            is_completed=False,
            priority="none",
            created_by=user_id,
        )
        db.add(no_due)
        await db.flush()

        source = ReminderCardSource(workspace_id=ws_id, db=db)
        cards = await source.fetch(today=TODAY, now=NOW)
        no_due_title = no_due.title
        await db.rollback()

    titles = {c.payload["title"] for c in cards}
    assert no_due_title in titles


# ---------------------------------------------------------------------------
# Integration tests: GET /api/v1/today
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_today_endpoint_requires_auth(client: AsyncClient, seed_user: dict):
    ws_id = seed_user["workspace_id"]
    response = await client.get(f"/api/v1/today?workspace_id={ws_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_today_endpoint_rejects_wrong_workspace(
    client: AsyncClient, auth_tokens: dict
):
    other_ws = uuid4()
    response = await client.get(
        f"/api/v1/today?workspace_id={other_ws}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_today_endpoint_returns_envelope(
    client: AsyncClient, auth_tokens: dict
):
    ws_id = auth_tokens["workspace_id"]
    response = await client.get(
        f"/api/v1/today?workspace_id={ws_id}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Validate envelope structure
    assert "cards" in data
    assert "sources" in data
    assert "metadata" in data
    assert data["metadata"]["query_path"] == "deterministic"

    # Status card is always present
    card_types = {c["type"] for c in data["cards"]}
    assert "status" in card_types


@pytest.mark.asyncio
async def test_today_cards_sorted_by_priority_desc(
    client: AsyncClient,
    auth_tokens: dict,
    test_session_factory,
):
    ws_id = auth_tokens["workspace_id"]
    user_id = auth_tokens["user_id"]

    # Seed an overdue reminder (score 1.0) and a future event (score ~0.65)
    async with test_session_factory() as db:
        src = await _make_calendar_source(db, auth_tokens)
        overdue = Reminder(
            workspace_id=ws_id,
            title=f"Overdue {uuid4().hex[:6]}",
            due_at=datetime.now(timezone.utc) - timedelta(hours=3),
            is_completed=False,
            priority="high",
            created_by=user_id,
        )
        future_event = CalendarEvent(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ev-sort-{uuid4().hex[:8]}",
            title="Future event",
            start_at=datetime.now(timezone.utc) + timedelta(hours=5),
            end_at=datetime.now(timezone.utc) + timedelta(hours=6),
            is_all_day=False,
        )
        db.add_all([overdue, future_event])
        await db.commit()

    response = await client.get(
        f"/api/v1/today?workspace_id={ws_id}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    cards = response.json()["cards"]

    scores = [c["priority_score"] for c in cards]
    assert scores == sorted(scores, reverse=True), "Cards not sorted descending by priority_score"
