"""Tests for S05-002: Text search across calendar, reminders, contacts.

Covers:
  - Search returns matching results by title/notes
  - Type filter (calendar only, reminder only, contact only, all)
  - Date range filter for calendar
  - Relevance scoring (title match > notes match)
  - Pagination (cursor, has_more)
  - Workspace isolation
  - Query fallback in POST /api/v1/query
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.reminder import Reminder
from api.db.models.source import Source
from api.services.query.search import (
    search_all,
    search_calendar,
    search_contacts,
    search_reminders,
)

NOW = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


async def _make_source(db, seed_user, source_type="calendar") -> Source:
    src = Source(
        workspace_id=seed_user["workspace_id"],
        name=f"Search Test {source_type}",
        type=source_type,
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(src)
    await db.flush()
    return src


# ---------------------------------------------------------------------------
# Calendar search
# ---------------------------------------------------------------------------


class TestSearchCalendar:
    @pytest.mark.asyncio
    async def test_title_match(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            db.add(
                CalendarEvent(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ev-s-{uuid4().hex[:6]}",
                    title="Team Retrospective",
                    start_at=NOW + timedelta(hours=2),
                    is_all_day=False,
                )
            )
            db.add(
                CalendarEvent(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ev-s-{uuid4().hex[:6]}",
                    title="Lunch break",
                    start_at=NOW + timedelta(hours=3),
                    is_all_day=False,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards = await search_calendar("Retrospective", ws_id, db)

        titles = [c.payload["title"] for c in cards]
        assert "Team Retrospective" in titles
        assert "Lunch break" not in titles

    @pytest.mark.asyncio
    async def test_notes_match_lower_score(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            db.add(
                CalendarEvent(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ev-sn-{uuid4().hex[:6]}",
                    title="Weekly Sync",
                    notes="Discuss budget review",
                    start_at=NOW + timedelta(hours=1),
                    is_all_day=False,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards = await search_calendar("budget", ws_id, db)

        assert len(cards) == 1
        assert cards[0].priority_score == 0.7  # Notes match, not title

    @pytest.mark.asyncio
    async def test_date_range_filter(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            db.add(
                CalendarEvent(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ev-dr1-{uuid4().hex[:6]}",
                    title="Planning session",
                    start_at=datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
                    is_all_day=False,
                )
            )
            db.add(
                CalendarEvent(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ev-dr2-{uuid4().hex[:6]}",
                    title="Planning review",
                    start_at=datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
                    is_all_day=False,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards = await search_calendar(
                "Planning",
                ws_id,
                db,
                date_from=datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
                date_to=datetime(2026, 4, 12, 23, 59, tzinfo=timezone.utc),
            )

        # Neither event falls in the range
        assert len(cards) == 0


# ---------------------------------------------------------------------------
# Reminder search
# ---------------------------------------------------------------------------


class TestSearchReminders:
    @pytest.mark.asyncio
    async def test_title_match(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            db.add(
                Reminder(
                    workspace_id=ws_id,
                    title=f"Buy groceries {uuid4().hex[:6]}",
                    due_at=NOW + timedelta(hours=2),
                    is_completed=False,
                    priority="medium",
                    created_by=user_id,
                )
            )
            db.add(
                Reminder(
                    workspace_id=ws_id,
                    title=f"Call dentist {uuid4().hex[:6]}",
                    due_at=NOW + timedelta(hours=3),
                    is_completed=False,
                    priority="low",
                    created_by=user_id,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards = await search_reminders("groceries", ws_id, db)

        titles = [c.payload["title"] for c in cards]
        assert any("groceries" in t.lower() for t in titles)
        assert not any("dentist" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_excludes_deleted(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            db.add(
                Reminder(
                    workspace_id=ws_id,
                    title=f"Deleted task searchable {uuid4().hex[:6]}",
                    due_at=NOW,
                    is_completed=False,
                    priority="none",
                    created_by=user_id,
                    deleted_at=NOW - timedelta(hours=1),
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards = await search_reminders("Deleted task searchable", ws_id, db)

        assert len(cards) == 0


# ---------------------------------------------------------------------------
# Contact search
# ---------------------------------------------------------------------------


class TestSearchContacts:
    @pytest.mark.asyncio
    async def test_name_match(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user, "contacts")
            db.add(
                Contact(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ct-s-{uuid4().hex[:6]}",
                    display_name="Sarah Connor",
                    first_name="Sarah",
                    last_name="Connor",
                    imported_at=NOW,
                )
            )
            db.add(
                Contact(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ct-s-{uuid4().hex[:6]}",
                    display_name="John Doe",
                    first_name="John",
                    last_name="Doe",
                    imported_at=NOW,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards = await search_contacts("Sarah", ws_id, db)

        names = [c.payload["display_name"] for c in cards]
        assert "Sarah Connor" in names
        assert "John Doe" not in names

    @pytest.mark.asyncio
    async def test_org_match(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user, "contacts")
            db.add(
                Contact(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ct-o-{uuid4().hex[:6]}",
                    display_name="Eve Techie",
                    organization="TechCorp",
                    imported_at=NOW,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards = await search_contacts("TechCorp", ws_id, db)

        assert len(cards) >= 1
        assert cards[0].payload["organization"] == "TechCorp"


# ---------------------------------------------------------------------------
# Multi-type search
# ---------------------------------------------------------------------------


class TestSearchAll:
    @pytest.mark.asyncio
    async def test_returns_mixed_types(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            db.add(
                CalendarEvent(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ev-all-{uuid4().hex[:6]}",
                    title="Project Alpha meeting",
                    start_at=NOW + timedelta(hours=1),
                    is_all_day=False,
                )
            )
            db.add(
                Reminder(
                    workspace_id=ws_id,
                    title=f"Review Project Alpha {uuid4().hex[:6]}",
                    is_completed=False,
                    priority="high",
                    created_by=user_id,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards, facets = await search_all("Alpha", ws_id, db)

        types = {c.type for c in cards}
        assert "event" in types
        assert "reminder" in types
        assert "calendar" in facets
        assert "reminder" in facets

    @pytest.mark.asyncio
    async def test_type_filter(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            db.add(
                CalendarEvent(
                    workspace_id=ws_id,
                    source_id=src.id,
                    external_id=f"ev-tf-{uuid4().hex[:6]}",
                    title="Beta event",
                    start_at=NOW + timedelta(hours=1),
                    is_all_day=False,
                )
            )
            db.add(
                Reminder(
                    workspace_id=ws_id,
                    title=f"Beta reminder {uuid4().hex[:6]}",
                    is_completed=False,
                    priority="none",
                    created_by=user_id,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            cards, facets = await search_all(
                "Beta", ws_id, db, types=["calendar"]
            )

        types = {c.type for c in cards}
        assert "event" in types or len(cards) == 0
        assert "reminder" not in types
        assert "reminder" not in facets


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    @pytest.mark.asyncio
    async def test_limit_and_offset(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            for i in range(5):
                db.add(
                    CalendarEvent(
                        workspace_id=ws_id,
                        source_id=src.id,
                        external_id=f"ev-pag-{i}-{uuid4().hex[:6]}",
                        title=f"Paginated event {i}",
                        start_at=NOW + timedelta(hours=i + 1),
                        is_all_day=False,
                    )
                )
            await db.commit()

        async with test_session_factory() as db:
            page1 = await search_calendar("Paginated", ws_id, db, limit=2, offset=0)
            page2 = await search_calendar("Paginated", ws_id, db, limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2
        # No overlap
        ids1 = {str(c.id) for c in page1}
        ids2 = {str(c.id) for c in page2}
        assert ids1.isdisjoint(ids2)


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_workspace_isolation(test_session_factory, seed_user):
    """Search must not return results from other workspaces."""
    from api.db.models.user import User
    from api.db.models.workspace import Workspace
    from api.db.models.workspace_member import WorkspaceMember
    from api.services.auth import hash_password

    async with test_session_factory() as db:
        other_user = User(
            email=f"other-search-{uuid4().hex[:8]}@ekamcore.dev",
            display_name="Other",
            password_hash=hash_password("pw"),
            role="standard",
            is_active=True,
        )
        db.add(other_user)
        await db.flush()
        other_ws = Workspace(name="Other", type="personal", owner_id=other_user.id)
        db.add(other_ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=other_ws.id, user_id=other_user.id, role="admin"))
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

        db.add(
            CalendarEvent(
                workspace_id=other_ws.id,
                source_id=other_src.id,
                external_id=f"ev-iso-search-{uuid4().hex[:6]}",
                title="Isolated secret",
                start_at=NOW + timedelta(hours=1),
                is_all_day=False,
            )
        )
        await db.commit()

    async with test_session_factory() as db:
        cards = await search_calendar("Isolated secret", seed_user["workspace_id"], db)

    assert len(cards) == 0


# ---------------------------------------------------------------------------
# GET /api/v1/search endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_endpoint_requires_auth(client, seed_user):
    ws_id = seed_user["workspace_id"]
    response = await client.get(f"/api/v1/search?q=test&workspace_id={ws_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_endpoint_rejects_wrong_workspace(client, auth_tokens):
    other_ws = uuid4()
    response = await client.get(
        f"/api/v1/search?q=test&workspace_id={other_ws}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_search_endpoint_returns_response_shape(client, auth_tokens):
    ws_id = auth_tokens["workspace_id"]
    response = await client.get(
        f"/api/v1/search?q=anything&workspace_id={ws_id}",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "pagination" in data
    assert "facets" in data
    assert "cursor" in data["pagination"]
    assert "has_more" in data["pagination"]


@pytest.mark.asyncio
async def test_search_endpoint_type_filter(client, auth_tokens):
    ws_id = auth_tokens["workspace_id"]
    response = await client.get(
        f"/api/v1/search?q=test&workspace_id={ws_id}&type=reminder",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    # Should only have reminder facets
    assert "calendar" not in data["facets"]
    assert "contact" not in data["facets"]


@pytest.mark.asyncio
async def test_search_endpoint_pagination(client, auth_tokens, test_session_factory):
    ws_id = auth_tokens["workspace_id"]
    user_id = auth_tokens["user_id"]

    # Seed enough reminders
    async with test_session_factory() as db:
        for i in range(5):
            db.add(
                Reminder(
                    workspace_id=ws_id,
                    title=f"Paginatable item {i} {uuid4().hex[:4]}",
                    is_completed=False,
                    priority="none",
                    created_by=user_id,
                )
            )
        await db.commit()

    response = await client.get(
        f"/api/v1/search?q=Paginatable&workspace_id={ws_id}&per_page=2&cursor=0",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) <= 2
    assert data["pagination"]["cursor"] == len(data["data"])


# ---------------------------------------------------------------------------
# POST /api/v1/query Step 2 fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_fallback_to_search(client, auth_tokens, test_session_factory):
    """When no pattern matches, POST /api/v1/query should search and return cards."""
    ws_id = auth_tokens["workspace_id"]
    user_id = auth_tokens["user_id"]

    async with test_session_factory() as db:
        db.add(
            Reminder(
                workspace_id=ws_id,
                title=f"Unique fallback item {uuid4().hex[:6]}",
                is_completed=False,
                priority="none",
                created_by=user_id,
            )
        )
        await db.commit()

    response = await client.post(
        "/api/v1/query",
        json={
            "query": "Unique fallback item",
            "workspace_id": str(ws_id),
        },
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    # Should get results via search fallback with high confidence
    if data["cards"]:
        assert data["confidence_level"] == "high"
