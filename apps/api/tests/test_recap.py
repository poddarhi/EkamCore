"""Tests for S04-008: Recap endpoint — daily/weekly card grouping.

Covers:
  - Daily recap returns events + completed reminders + newly overdue for a date
  - Weekly recap aggregates 7 days of data
  - Empty day returns envelope with zero cards
  - Cache hit returns same envelope without re-querying
  - Auth/workspace validation
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from api.db.models.calendar_event import CalendarEvent
from api.db.models.reminder import Reminder
from api.db.models.source import Source
from api.services.recap.generator import (
    _cache_key,
    _fetch_completed_reminders,
    _fetch_events_for_range,
    _fetch_newly_overdue_reminders,
    generate_recap,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YESTERDAY = date(2026, 4, 8)
NOW = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_source(db, seed_user: dict) -> Source:
    src = Source(
        workspace_id=seed_user["workspace_id"],
        name="Recap Test Calendar",
        type="calendar",
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(src)
    await db.flush()
    return src


def _redis_mock(cached_value: str | None = None) -> MagicMock:
    mock = MagicMock()
    mock.get = AsyncMock(return_value=cached_value)
    mock.setex = AsyncMock(return_value=True)
    return mock


# ---------------------------------------------------------------------------
# Unit tests: fetch functions
# ---------------------------------------------------------------------------


class TestFetchEventsForRange:
    @pytest.mark.asyncio
    async def test_returns_events_within_range(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)

            in_range = CalendarEvent(
                workspace_id=ws_id,
                source_id=src.id,
                external_id=f"ev-in-{uuid4().hex[:6]}",
                title="Yesterday standup",
                start_at=datetime(2026, 4, 8, 9, 0, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 8, 9, 30, 0, tzinfo=timezone.utc),
                is_all_day=False,
            )
            out_of_range = CalendarEvent(
                workspace_id=ws_id,
                source_id=src.id,
                external_id=f"ev-out-{uuid4().hex[:6]}",
                title="Today meeting",
                start_at=datetime(2026, 4, 9, 14, 0, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 15, 0, 0, tzinfo=timezone.utc),
                is_all_day=False,
            )
            db.add_all([in_range, out_of_range])
            await db.flush()

            cards = await _fetch_events_for_range(db, ws_id, YESTERDAY, YESTERDAY)
            await db.rollback()

        titles = [c.payload["title"] for c in cards]
        assert "Yesterday standup" in titles
        assert "Today meeting" not in titles

    @pytest.mark.asyncio
    async def test_empty_range_returns_no_cards(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            cards = await _fetch_events_for_range(
                db, ws_id, date(2020, 1, 1), date(2020, 1, 1)
            )
            await db.rollback()

        assert cards == []


class TestFetchCompletedReminders:
    @pytest.mark.asyncio
    async def test_returns_completed_in_range(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            completed_yesterday = Reminder(
                workspace_id=ws_id,
                title=f"Done yesterday {uuid4().hex[:6]}",
                due_at=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
                is_completed=True,
                completed_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
                priority="none",
                created_by=user_id,
            )
            completed_today = Reminder(
                workspace_id=ws_id,
                title=f"Done today {uuid4().hex[:6]}",
                due_at=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
                is_completed=True,
                completed_at=datetime(2026, 4, 9, 11, 0, tzinfo=timezone.utc),
                priority="none",
                created_by=user_id,
            )
            incomplete = Reminder(
                workspace_id=ws_id,
                title=f"Still pending {uuid4().hex[:6]}",
                due_at=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
                is_completed=False,
                priority="none",
                created_by=user_id,
            )
            db.add_all([completed_yesterday, completed_today, incomplete])
            await db.flush()

            cards = await _fetch_completed_reminders(db, ws_id, YESTERDAY, YESTERDAY)
            y_title = completed_yesterday.title
            t_title = completed_today.title
            i_title = incomplete.title
            await db.rollback()

        titles = [c.payload["title"] for c in cards]
        assert y_title in titles
        assert t_title not in titles
        assert i_title not in titles


class TestFetchNewlyOverdueReminders:
    @pytest.mark.asyncio
    async def test_returns_overdue_in_range(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            overdue = Reminder(
                workspace_id=ws_id,
                title=f"Missed deadline {uuid4().hex[:6]}",
                due_at=datetime(2026, 4, 8, 17, 0, tzinfo=timezone.utc),
                is_completed=False,
                priority="high",
                created_by=user_id,
            )
            completed_overdue = Reminder(
                workspace_id=ws_id,
                title=f"Was late but done {uuid4().hex[:6]}",
                due_at=datetime(2026, 4, 8, 17, 0, tzinfo=timezone.utc),
                is_completed=True,
                completed_at=datetime(2026, 4, 9, 8, 0, tzinfo=timezone.utc),
                priority="none",
                created_by=user_id,
            )
            db.add_all([overdue, completed_overdue])
            await db.flush()

            cards = await _fetch_newly_overdue_reminders(db, ws_id, YESTERDAY, YESTERDAY)
            overdue_title = overdue.title
            done_title = completed_overdue.title
            await db.rollback()

        titles = [c.payload["title"] for c in cards]
        assert overdue_title in titles
        assert done_title not in titles

        # Verify is_overdue flag
        for card in cards:
            if card.payload["title"] == overdue_title:
                assert card.payload["is_overdue"] is True


# ---------------------------------------------------------------------------
# Integration tests: generate_recap
# ---------------------------------------------------------------------------


class TestGenerateRecap:
    @pytest.mark.asyncio
    async def test_daily_returns_all_card_types(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)

            event = CalendarEvent(
                workspace_id=ws_id,
                source_id=src.id,
                external_id=f"ev-recap-{uuid4().hex[:6]}",
                title="Recap event",
                start_at=datetime(2026, 4, 8, 14, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc),
                is_all_day=False,
            )
            completed = Reminder(
                workspace_id=ws_id,
                title=f"Recap completed {uuid4().hex[:6]}",
                due_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
                is_completed=True,
                completed_at=datetime(2026, 4, 8, 12, 30, tzinfo=timezone.utc),
                priority="medium",
                created_by=user_id,
            )
            overdue = Reminder(
                workspace_id=ws_id,
                title=f"Recap overdue {uuid4().hex[:6]}",
                due_at=datetime(2026, 4, 8, 18, 0, tzinfo=timezone.utc),
                is_completed=False,
                priority="high",
                created_by=user_id,
            )
            db.add_all([event, completed, overdue])
            await db.commit()

            redis_mock = _redis_mock()
            with patch("api.services.recap.generator.get_redis", return_value=redis_mock):
                envelope = await generate_recap(
                    workspace_id=ws_id,
                    db=db,
                    period="daily",
                    target_date=YESTERDAY,
                )

        assert len(envelope.cards) == 3
        card_types = {c.type for c in envelope.cards}
        assert "event" in card_types
        assert "reminder" in card_types
        assert envelope.metadata.query_path == "deterministic"
        assert envelope.metadata.cache_hint is not None
        assert envelope.metadata.cache_hint.ttl_seconds == 3600

    @pytest.mark.asyncio
    async def test_weekly_aggregates_7_days(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)

            # Events on day 1 and day 7 of the week
            day1_event = CalendarEvent(
                workspace_id=ws_id,
                source_id=src.id,
                external_id=f"ev-w1-{uuid4().hex[:6]}",
                title="Week start event",
                start_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 2, 11, 0, tzinfo=timezone.utc),
                is_all_day=False,
            )
            day7_event = CalendarEvent(
                workspace_id=ws_id,
                source_id=src.id,
                external_id=f"ev-w7-{uuid4().hex[:6]}",
                title="Week end event",
                start_at=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
                is_all_day=False,
            )
            db.add_all([day1_event, day7_event])
            await db.commit()

            redis_mock = _redis_mock()
            with patch("api.services.recap.generator.get_redis", return_value=redis_mock):
                envelope = await generate_recap(
                    workspace_id=ws_id,
                    db=db,
                    period="weekly",
                    target_date=YESTERDAY,
                )

        titles = {c.payload["title"] for c in envelope.cards}
        assert "Week start event" in titles
        assert "Week end event" in titles

    @pytest.mark.asyncio
    async def test_empty_day_returns_zero_cards(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            redis_mock = _redis_mock()
            with patch("api.services.recap.generator.get_redis", return_value=redis_mock):
                envelope = await generate_recap(
                    workspace_id=ws_id,
                    db=db,
                    period="daily",
                    target_date=date(2020, 1, 1),
                )

        assert len(envelope.cards) == 0
        assert envelope.metadata.query_path == "deterministic"

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_envelope(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        # Build a minimal cached envelope
        cached_envelope = {
            "answer_text": None,
            "confidence_level": "deterministic",
            "sources": [],
            "cards": [],
            "suggested_actions": [],
            "metadata": {
                "query_path": "deterministic",
                "latency_ms": 5,
                "is_partial": False,
                "cache_hint": {"ttl_seconds": 3600},
            },
        }

        async with test_session_factory() as db:
            redis_mock = _redis_mock(cached_value=json.dumps(cached_envelope))
            with patch("api.services.recap.generator.get_redis", return_value=redis_mock):
                envelope = await generate_recap(
                    workspace_id=ws_id,
                    db=db,
                    period="daily",
                    target_date=YESTERDAY,
                )

        # Should have returned without querying DB
        assert envelope.cards == []
        assert envelope.metadata.query_path == "deterministic"
        # Cache was read but setex should NOT have been called (cache hit)
        redis_mock.setex.assert_not_awaited()


# ---------------------------------------------------------------------------
# Integration tests: GET /api/v1/recap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recap_endpoint_requires_auth(client, seed_user):
    ws_id = seed_user["workspace_id"]
    response = await client.get(f"/api/v1/recap?workspace_id={ws_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_recap_endpoint_rejects_wrong_workspace(client, auth_tokens):
    other_ws = uuid4()
    response = await client.get(
        f"/api/v1/recap?workspace_id={other_ws}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_recap_endpoint_returns_envelope(client, auth_tokens):
    ws_id = auth_tokens["workspace_id"]

    redis_mock = _redis_mock()
    with patch("api.services.recap.generator.get_redis", return_value=redis_mock):
        response = await client.get(
            f"/api/v1/recap?workspace_id={ws_id}&period=daily&date=2026-04-08",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "cards" in data
    assert "metadata" in data
    assert data["metadata"]["query_path"] == "deterministic"


@pytest.mark.asyncio
async def test_recap_endpoint_default_period_is_daily(client, auth_tokens):
    ws_id = auth_tokens["workspace_id"]

    redis_mock = _redis_mock()
    with patch("api.services.recap.generator.get_redis", return_value=redis_mock):
        response = await client.get(
            f"/api/v1/recap?workspace_id={ws_id}",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Cache key format
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_daily_key_format(self):
        ws = uuid4()
        key = _cache_key(ws, "daily", date(2026, 4, 8))
        assert key == f"recap:{ws}:daily:2026-04-08"

    def test_weekly_key_format(self):
        ws = uuid4()
        key = _cache_key(ws, "weekly", date(2026, 4, 8))
        assert key == f"recap:{ws}:weekly:2026-04-08"
