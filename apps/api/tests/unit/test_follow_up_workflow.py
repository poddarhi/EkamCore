"""Unit tests for the PLA follow-up suggestion workflow (S14-006).

Stubs PackContext methods via AsyncMock to exercise the scoring,
filtering, dedup, and snooze logic without touching the DB.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

# Make packs importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packs"))

from pla.workflows.follow_up import run_follow_up_suggestions

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _person(name: str, pid=None):
    return SimpleNamespace(
        id=pid or uuid4(),
        display_name=name,
        workspace_id=uuid4(),
    )


def _edge(edge_type: str, days_ago: int):
    return SimpleNamespace(
        edge_type=edge_type,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        to_type="photo_asset" if edge_type == "appears_in" else "calendar_event",
        to_id=uuid4(),
        from_type="trusted_person",
        from_id=uuid4(),
    )


def _build_ctx(
    *,
    persons=None,
    edges_by_person=None,
    upcoming_events=None,
    has_pending=False,
    is_snoozed=False,
):
    ctx = AsyncMock()
    ctx.workspace_id = uuid4()
    ctx.get_persons = AsyncMock(return_value=persons or [])
    ctx.get_events_in_range = AsyncMock(
        return_value=upcoming_events or []
    )

    async def _get_edges(pid, **kw):
        return (edges_by_person or {}).get(pid, [])

    ctx.get_edges_for_person = AsyncMock(side_effect=_get_edges)
    ctx.has_pending_card_for_person = AsyncMock(return_value=has_pending)
    ctx.is_person_snoozed = AsyncMock(return_value=is_snoozed)
    ctx.produce_card = AsyncMock()
    return ctx


class TestSuggestionProduced:
    async def test_person_with_old_interaction_gets_suggestion(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={alice.id: [_edge("appears_in", 10)]},
        )
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_awaited_once()
        call_args = ctx.produce_card.call_args
        assert call_args[0][0] == "follow_up_suggestion"
        payload = call_args[0][1]
        assert payload["person_display_name"] == "Alice"
        assert payload["days_since_last_interaction"] >= 10


class TestSkipRecent:
    async def test_person_with_recent_interaction_is_skipped(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={alice.id: [_edge("appears_in", 3)]},
        )
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_not_awaited()


class TestSkipUpcoming:
    async def test_person_with_upcoming_event_is_skipped(self):
        alice = _person("Alice")
        event = SimpleNamespace(
            participants_json=[{"name": "Alice"}],
            start_at=datetime.now(timezone.utc) + timedelta(days=2),
        )
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={alice.id: [_edge("attended", 15)]},
            upcoming_events=[event],
        )
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_not_awaited()


class TestMaxSuggestions:
    async def test_only_top_5_when_10_qualify(self):
        persons = [_person(f"P{i}") for i in range(10)]
        edges = {
            p.id: [_edge("appears_in", 10 + i)]
            for i, p in enumerate(persons)
        }
        ctx = _build_ctx(persons=persons, edges_by_person=edges)
        await run_follow_up_suggestions(ctx)
        assert ctx.produce_card.await_count == 5


class TestDedup:
    async def test_existing_card_today_prevents_duplicate(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={alice.id: [_edge("appears_in", 10)]},
            has_pending=True,
        )
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_not_awaited()


class TestSnooze:
    async def test_snoozed_person_is_skipped(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={alice.id: [_edge("appears_in", 10)]},
            is_snoozed=True,
        )
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_not_awaited()


class TestNoPersons:
    async def test_empty_persons_produces_nothing(self):
        ctx = _build_ctx(persons=[])
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_not_awaited()


class TestNoInteractionData:
    async def test_person_with_no_edges_is_skipped(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={alice.id: []},
        )
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_not_awaited()

    async def test_person_with_only_non_interaction_edges(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={
                alice.id: [_edge("associated_with", 20)]
            },
        )
        await run_follow_up_suggestions(ctx)
        ctx.produce_card.assert_not_awaited()


class TestPriorityRanking:
    async def test_most_overdue_person_ranked_first(self):
        alice = _person("Alice")
        bob = _person("Bob")
        ctx = _build_ctx(
            persons=[alice, bob],
            edges_by_person={
                alice.id: [_edge("appears_in", 20)],
                bob.id: [_edge("appears_in", 10)],
            },
        )
        await run_follow_up_suggestions(ctx)
        assert ctx.produce_card.await_count == 2
        first_payload = ctx.produce_card.call_args_list[0][0][1]
        assert first_payload["person_display_name"] == "Alice"
