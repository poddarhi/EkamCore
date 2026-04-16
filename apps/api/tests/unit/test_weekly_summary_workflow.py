"""Unit tests for the PLA weekly summary workflow (S14-007).

Stubs PackContext via AsyncMock. Exercises the LLM success path,
parse-failure fallback, LLM-unavailable fallback, dedup, and the
empty-week edge case.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

# Make packs importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packs"))

from pla.workflows.weekly_summary import (
    _fallback_summary,
    _parse_llm_response,
    _week_range,
    run_weekly_summary,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _person(name: str, pid=None):
    return SimpleNamespace(
        id=pid or uuid4(),
        display_name=name,
    )


def _edge(edge_type: str, days_ago: int):
    return SimpleNamespace(
        edge_type=edge_type,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def _reminder(*, completed: bool, days_ago: int = 1):
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return SimpleNamespace(
        completed_at=ts if completed else None,
        created_at=ts,
    )


def _photo(days_ago: int = 1):
    return SimpleNamespace(
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def _file(days_ago: int = 1):
    return SimpleNamespace(
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def _build_ctx(
    *,
    persons=None,
    edges_by_person=None,
    events=None,
    reminders=None,
    photos=None,
    files=None,
    llm_response: str | Exception = '{"summary": "Great week!"}',
    has_pending=False,
):
    ctx = AsyncMock()
    ctx.workspace_id = uuid4()
    ctx.get_persons = AsyncMock(return_value=persons or [])
    ctx.get_events_in_range = AsyncMock(return_value=events or [])
    ctx.get_reminders = AsyncMock(return_value=reminders or [])
    ctx.get_photos = AsyncMock(return_value=photos or [])
    ctx.get_files = AsyncMock(return_value=files or [])
    ctx.has_pending_card_for_person = AsyncMock(return_value=has_pending)
    ctx.is_person_snoozed = AsyncMock(return_value=False)

    async def _get_edges(pid, **kw):
        return (edges_by_person or {}).get(pid, [])

    ctx.get_edges_for_person = AsyncMock(side_effect=_get_edges)

    if isinstance(llm_response, Exception):
        ctx.ask_llm = AsyncMock(side_effect=llm_response)
    else:
        ctx.ask_llm = AsyncMock(return_value=llm_response)

    ctx.produce_card = AsyncMock()
    return ctx


# ── Time helpers ──────────────────────────────────────────────────────────


class TestWeekRange:
    def test_monday_returns_same_week(self):
        from datetime import date

        mon, sun = _week_range(date(2026, 4, 13))  # Monday
        assert mon.weekday() == 0
        assert sun.weekday() == 6
        assert mon <= date(2026, 4, 13) <= sun

    def test_wednesday_returns_same_week(self):
        from datetime import date

        mon, sun = _week_range(date(2026, 4, 15))  # Wednesday
        assert mon == date(2026, 4, 13)
        assert sun == date(2026, 4, 19)


class TestParseResponse:
    def test_valid_json(self):
        assert _parse_llm_response('{"summary": "Hello!"}') == "Hello!"

    def test_json_in_markdown_fences(self):
        raw = '```json\n{"summary": "Hello!"}\n```'
        assert _parse_llm_response(raw) == "Hello!"

    def test_invalid_json(self):
        assert _parse_llm_response("not json at all") is None

    def test_missing_summary_key(self):
        assert _parse_llm_response('{"text": "hi"}') is None

    def test_empty_summary(self):
        assert _parse_llm_response('{"summary": ""}') is None


class TestFallbackSummary:
    def test_with_events_and_persons(self):
        s = _fallback_summary(
            {
                "events_count": 3,
                "persons_seen": 5,
                "new_photos": 10,
                "top_persons": [{"name": "Alice"}, {"name": "Bob"}],
            }
        )
        assert "3 events" in s
        assert "5 people" in s
        assert "Alice" in s

    def test_quiet_week(self):
        s = _fallback_summary(
            {
                "events_count": 0,
                "persons_seen": 0,
                "new_photos": 0,
                "top_persons": [],
            }
        )
        assert "quiet" in s.lower()


# ── Workflow tests ────────────────────────────────────────────────────────


class TestLlmSuccess:
    async def test_produces_card_with_llm_summary(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={alice.id: [_edge("appears_in", 2)]},
            events=[],
            photos=[_photo(1)],
            llm_response='{"summary": "You saw Alice this week."}',
        )
        await run_weekly_summary(ctx)
        ctx.produce_card.assert_awaited_once()
        payload = ctx.produce_card.call_args[0][1]
        assert payload["llm_generated"] is True
        assert payload["summary_text"] == "You saw Alice this week."
        assert "week_start" in payload
        assert "stats" in payload


class TestLlmParseFailure:
    async def test_falls_back_to_template_on_bad_json(self):
        ctx = _build_ctx(
            persons=[_person("X")],
            edges_by_person={},
            llm_response="This is not JSON at all!",
        )
        await run_weekly_summary(ctx)
        ctx.produce_card.assert_awaited_once()
        payload = ctx.produce_card.call_args[0][1]
        assert payload["llm_generated"] is False
        assert isinstance(payload["summary_text"], str)
        assert len(payload["summary_text"]) > 0


class TestLlmUnavailable:
    async def test_falls_back_on_llm_exception(self):
        ctx = _build_ctx(
            persons=[],
            llm_response=RuntimeError("Ollama down"),
        )
        await run_weekly_summary(ctx)
        ctx.produce_card.assert_awaited_once()
        payload = ctx.produce_card.call_args[0][1]
        assert payload["llm_generated"] is False


class TestDedup:
    async def test_existing_card_this_week_prevents_duplicate(self):
        ctx = _build_ctx(has_pending=True)
        await run_weekly_summary(ctx)
        ctx.produce_card.assert_not_awaited()


class TestEmptyWeek:
    async def test_quiet_week_still_produces_card(self):
        ctx = _build_ctx(
            persons=[],
            events=[],
            reminders=[],
            photos=[],
            files=[],
            llm_response=RuntimeError("no LLM"),
        )
        await run_weekly_summary(ctx)
        ctx.produce_card.assert_awaited_once()
        payload = ctx.produce_card.call_args[0][1]
        assert "quiet" in payload["summary_text"].lower()
