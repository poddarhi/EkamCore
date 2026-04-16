"""Unit tests for the PLA relationship reminder workflow (S14-008)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packs"))

from pla.workflows.relationship_reminder import (
    _relationship_context,
    run_relationship_reminders,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _person(name: str, pid=None):
    return SimpleNamespace(id=pid or uuid4(), display_name=name)


def _edge(edge_type: str, days_ago: int, strength: float = 0.7):
    return SimpleNamespace(
        edge_type=edge_type,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        strength=strength,
    )


def _build_ctx(
    *,
    persons=None,
    edges_by_person=None,
    has_follow_up=False,
    has_reminder=False,
    is_snoozed=False,
):
    ctx = AsyncMock()
    ctx.workspace_id = uuid4()
    ctx.get_persons = AsyncMock(return_value=persons or [])

    async def _get_edges(pid, **kw):
        return (edges_by_person or {}).get(pid, [])

    ctx.get_edges_for_person = AsyncMock(side_effect=_get_edges)

    async def _has_pending(pid, card_type, target_date):
        if card_type == "follow_up_suggestion":
            return has_follow_up
        if card_type == "relationship_reminder":
            return has_reminder
        return False

    ctx.has_pending_card_for_person = AsyncMock(side_effect=_has_pending)
    ctx.is_person_snoozed = AsyncMock(return_value=is_snoozed)
    ctx.produce_card = AsyncMock()
    return ctx


class TestReminderProduced:
    async def test_strong_connection_long_inactive_produces_card(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={
                alice.id: [
                    _edge("appears_in", 45, strength=0.8),
                    _edge("attended", 50, strength=0.9),
                ]
            },
        )
        await run_relationship_reminders(ctx)
        ctx.produce_card.assert_awaited_once()
        payload = ctx.produce_card.call_args[0][1]
        assert payload["person_display_name"] == "Alice"
        assert payload["days_since_last_interaction"] >= 45
        assert payload["graph_strength"] >= 0.5


class TestWeakConnectionSkipped:
    async def test_low_strength_person_is_skipped(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={
                alice.id: [_edge("appears_in", 45, strength=0.3)]
            },
        )
        await run_relationship_reminders(ctx)
        ctx.produce_card.assert_not_awaited()


class TestRecentSkipped:
    async def test_recently_active_strong_connection_skipped(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={
                alice.id: [_edge("appears_in", 15, strength=0.9)]
            },
        )
        await run_relationship_reminders(ctx)
        ctx.produce_card.assert_not_awaited()


class TestFollowUpDedup:
    async def test_person_with_follow_up_today_is_skipped(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={
                alice.id: [_edge("appears_in", 45, strength=0.8)]
            },
            has_follow_up=True,
        )
        await run_relationship_reminders(ctx)
        ctx.produce_card.assert_not_awaited()


class TestSnooze:
    async def test_snoozed_person_skipped(self):
        alice = _person("Alice")
        ctx = _build_ctx(
            persons=[alice],
            edges_by_person={
                alice.id: [_edge("appears_in", 45, strength=0.8)]
            },
            is_snoozed=True,
        )
        await run_relationship_reminders(ctx)
        ctx.produce_card.assert_not_awaited()


class TestUrgencyRanking:
    async def test_higher_urgency_ranked_first(self):
        alice = _person("Alice")
        bob = _person("Bob")
        ctx = _build_ctx(
            persons=[alice, bob],
            edges_by_person={
                alice.id: [_edge("appears_in", 60, strength=0.9)],
                bob.id: [_edge("appears_in", 40, strength=0.6)],
            },
        )
        await run_relationship_reminders(ctx)
        assert ctx.produce_card.await_count == 2
        first = ctx.produce_card.call_args_list[0][0][1]
        # Alice: 0.9 * (60/30) = 1.8  |  Bob: 0.6 * (40/30) = 0.8
        assert first["person_display_name"] == "Alice"


class TestRelationshipContext:
    def test_photo_dominant(self):
        edges = [
            SimpleNamespace(edge_type="appears_in"),
            SimpleNamespace(edge_type="appears_in"),
            SimpleNamespace(edge_type="attended"),
        ]
        assert _relationship_context(edges) == "Many shared photos"

    def test_event_dominant(self):
        edges = [
            SimpleNamespace(edge_type="attended"),
            SimpleNamespace(edge_type="attended"),
            SimpleNamespace(edge_type="attended"),
        ]
        assert _relationship_context(edges) == "Frequent at events together"

    def test_document_present(self):
        edges = [
            SimpleNamespace(edge_type="appears_in"),
            SimpleNamespace(edge_type="associated_with"),
        ]
        assert _relationship_context(edges) == "Collaborated on documents"

    def test_mixed(self):
        edges = [
            SimpleNamespace(edge_type="appears_in"),
            SimpleNamespace(edge_type="attended"),
        ]
        assert _relationship_context(edges) == "Active in your network"


class TestNoPersons:
    async def test_empty_produces_nothing(self):
        ctx = _build_ctx(persons=[])
        await run_relationship_reminders(ctx)
        ctx.produce_card.assert_not_awaited()
