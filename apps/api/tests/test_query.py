"""Tests for S05-001: Deterministic query routing.

Covers:
  - Pattern matching: calendar, reminders, contacts, org search
  - Date parser: today, tomorrow, yesterday, this/next/last week
  - Query handler: parameterized SQL returns correct cards
  - Endpoint: auth, workspace isolation, pattern match, no-match fallback
  - SQL injection: verify parameterized queries (no string interpolation)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.reminder import Reminder
from api.db.models.source import Source
from api.services.query.date_parser import parse_date_reference
from api.services.query.patterns import QueryIntent, classify_query

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


async def _make_source(db, seed_user: dict, source_type: str = "calendar") -> Source:
    src = Source(
        workspace_id=seed_user["workspace_id"],
        name=f"Test {source_type}",
        type=source_type,
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(src)
    await db.flush()
    return src


# ---------------------------------------------------------------------------
# Date parser tests
# ---------------------------------------------------------------------------


class TestDateParser:
    def test_today(self):
        start, end = parse_date_reference("today", reference_date=TODAY)
        assert start.date() == TODAY
        assert end.date() == TODAY

    def test_tomorrow(self):
        start, end = parse_date_reference("tomorrow", reference_date=TODAY)
        assert start.date() == TODAY + timedelta(days=1)

    def test_yesterday(self):
        start, end = parse_date_reference("yesterday", reference_date=TODAY)
        assert start.date() == TODAY - timedelta(days=1)

    def test_this_week(self):
        start, end = parse_date_reference("this week", reference_date=TODAY)
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6    # Sunday
        assert start.date() <= TODAY <= end.date()

    def test_next_week(self):
        start, end = parse_date_reference("next week", reference_date=TODAY)
        assert start.date() > TODAY

    def test_last_week(self):
        start, end = parse_date_reference("last week", reference_date=TODAY)
        assert end.date() < TODAY

    def test_unknown_returns_none(self):
        assert parse_date_reference("in 3 months") is None

    def test_case_insensitive(self):
        result = parse_date_reference("Today", reference_date=TODAY)
        assert result is not None

    def test_whitespace_stripped(self):
        result = parse_date_reference("  today  ", reference_date=TODAY)
        assert result is not None


# ---------------------------------------------------------------------------
# Pattern matching tests
# ---------------------------------------------------------------------------


class TestPatternCalendar:
    def test_whats_on_calendar_today(self):
        intent = classify_query("what's on my calendar today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"
        assert intent.params["date_ref"] == "today"

    def test_what_is_on_calendar_tomorrow(self):
        intent = classify_query("what is on my calendar tomorrow")
        assert intent is not None
        assert intent.intent_type == "calendar_range"
        assert intent.params["date_ref"] == "tomorrow"

    def test_whats_on_calendar_this_week(self):
        intent = classify_query("what's on my calendar this week")
        assert intent is not None
        assert intent.params["date_ref"] == "this week"

    def test_meetings_today(self):
        intent = classify_query("meetings today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"
        assert intent.params["date_ref"] == "today"

    def test_events_tomorrow(self):
        intent = classify_query("events tomorrow")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_show_schedule_today(self):
        intent = classify_query("show my schedule for today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_do_i_have_meetings(self):
        intent = classify_query("do i have any meetings today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_appointments_next_week(self):
        intent = classify_query("appointments next week")
        assert intent is not None
        assert intent.intent_type == "calendar_range"
        assert intent.params["date_ref"] == "next week"


class TestPatternReminders:
    def test_show_reminders_due_today(self):
        intent = classify_query("show my reminders due today")
        assert intent is not None
        assert intent.intent_type == "reminders_range"
        assert intent.params["date_ref"] == "due today"

    def test_what_reminders_overdue(self):
        intent = classify_query("what reminders are overdue")
        assert intent is not None
        assert intent.intent_type == "reminders_range"

    def test_whats_due_today(self):
        intent = classify_query("what's due today")
        assert intent is not None
        assert intent.intent_type == "reminders_range"

    def test_whats_due_tomorrow(self):
        intent = classify_query("what is due tomorrow")
        assert intent is not None
        assert intent.intent_type == "reminders_range"

    def test_show_overdue_tasks(self):
        intent = classify_query("show me my overdue tasks")
        assert intent is not None
        assert intent.intent_type == "reminders_range"
        assert intent.params["date_ref"] == "overdue"

    def test_list_pending_reminders(self):
        intent = classify_query("list my pending reminders")
        assert intent is not None
        assert intent.intent_type == "reminders_range"


class TestPatternContacts:
    def test_find_contact_named(self):
        intent = classify_query("find contact named John Smith")
        assert intent is not None
        assert intent.intent_type == "contact_search"
        assert intent.params["name"] == "John Smith"

    def test_show_me_contact(self):
        intent = classify_query("show me contact Alice")
        assert intent is not None
        assert intent.intent_type == "contact_search"
        assert intent.params["name"] == "Alice"

    def test_who_is(self):
        intent = classify_query("who is Bob Johnson")
        assert intent is not None
        assert intent.intent_type == "contact_search"
        assert intent.params["name"] == "Bob Johnson"

    def test_who_works_at(self):
        intent = classify_query("who works at Acme Corp")
        assert intent is not None
        assert intent.intent_type == "contact_by_org"
        assert intent.params["organization"] == "Acme Corp"

    def test_people_at_org(self):
        intent = classify_query("contacts at Google")
        assert intent is not None
        assert intent.intent_type == "contact_by_org"
        assert intent.params["organization"] == "Google"


class TestPatternNoMatch:
    def test_empty_string(self):
        assert classify_query("") is None

    def test_gibberish(self):
        assert classify_query("asdfghjkl") is None

    def test_unhandled_question(self):
        assert classify_query("what is the meaning of life") is None

    def test_only_whitespace(self):
        assert classify_query("   ") is None


# ---------------------------------------------------------------------------
# Integration: calendar query handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_query_returns_matching_events(
    test_session_factory, seed_user
):
    ws_id = seed_user["workspace_id"]

    async with test_session_factory() as db:
        src = await _make_source(db, seed_user)

        today_event = CalendarEvent(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ev-q-{uuid4().hex[:6]}",
            title="Query test standup",
            start_at=datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc)
            + timedelta(hours=9),
            end_at=datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc)
            + timedelta(hours=10),
            is_all_day=False,
        )
        tomorrow_event = CalendarEvent(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ev-q-t-{uuid4().hex[:6]}",
            title="Tomorrow meeting",
            start_at=datetime.combine(
                TODAY + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
            )
            + timedelta(hours=14),
            end_at=datetime.combine(
                TODAY + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
            )
            + timedelta(hours=15),
            is_all_day=False,
        )
        db.add_all([today_event, tomorrow_event])
        await db.commit()

    from api.services.query.router import route_deterministic

    intent = classify_query("what's on my calendar today")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    titles = [c.payload["title"] for c in envelope.cards]
    assert "Query test standup" in titles
    assert "Tomorrow meeting" not in titles


# ---------------------------------------------------------------------------
# Integration: reminder query handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reminder_query_returns_overdue(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]
    user_id = seed_user["user_id"]

    async with test_session_factory() as db:
        overdue = Reminder(
            workspace_id=ws_id,
            title=f"Query overdue {uuid4().hex[:6]}",
            due_at=NOW - timedelta(hours=3),
            is_completed=False,
            priority="high",
            created_by=user_id,
        )
        completed = Reminder(
            workspace_id=ws_id,
            title=f"Query done {uuid4().hex[:6]}",
            due_at=NOW - timedelta(hours=2),
            is_completed=True,
            completed_at=NOW - timedelta(hours=1),
            priority="none",
            created_by=user_id,
        )
        db.add_all([overdue, completed])
        await db.commit()

        overdue_title = overdue.title
        done_title = completed.title

    from api.services.query.router import route_deterministic

    intent = classify_query("show me overdue reminders")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    titles = [c.payload["title"] for c in envelope.cards]
    assert overdue_title in titles
    assert done_title not in titles


# ---------------------------------------------------------------------------
# Integration: contact search handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_search_by_name(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]

    async with test_session_factory() as db:
        src = await _make_source(db, seed_user, "contacts")

        alice = Contact(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ct-{uuid4().hex[:6]}",
            display_name="Alice Wonderland",
            first_name="Alice",
            last_name="Wonderland",
            organization="Tea Party Inc",
            imported_at=NOW,
        )
        bob = Contact(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ct-{uuid4().hex[:6]}",
            display_name="Bob Builder",
            first_name="Bob",
            last_name="Builder",
            organization="Construction Co",
            imported_at=NOW,
        )
        db.add_all([alice, bob])
        await db.commit()

    from api.services.query.router import route_deterministic

    intent = classify_query("find contact named Alice")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    names = [c.payload["display_name"] for c in envelope.cards]
    assert "Alice Wonderland" in names
    assert "Bob Builder" not in names


@pytest.mark.asyncio
async def test_contact_search_by_org(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]

    async with test_session_factory() as db:
        src = await _make_source(db, seed_user, "contacts")

        c1 = Contact(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ct-org-{uuid4().hex[:6]}",
            display_name="Carol Acme",
            first_name="Carol",
            organization="Acme Corp",
            imported_at=NOW,
        )
        c2 = Contact(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ct-org-{uuid4().hex[:6]}",
            display_name="Dave Other",
            first_name="Dave",
            organization="Other LLC",
            imported_at=NOW,
        )
        db.add_all([c1, c2])
        await db.commit()

    from api.services.query.router import route_deterministic

    intent = classify_query("who works at Acme Corp")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    names = [c.payload["display_name"] for c in envelope.cards]
    assert "Carol Acme" in names
    assert "Dave Other" not in names


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_query_workspace_isolation(test_session_factory, seed_user):
    """Events in another workspace must not appear in query results."""
    from api.db.models.user import User
    from api.db.models.workspace import Workspace
    from api.db.models.workspace_member import WorkspaceMember
    from api.services.auth import hash_password
    from api.services.query.router import route_deterministic

    async with test_session_factory() as db:
        # Create other workspace
        other_user = User(
            email=f"other-q-{uuid4().hex[:8]}@ekamcore.dev",
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

        event = CalendarEvent(
            workspace_id=other_ws.id,
            source_id=other_src.id,
            external_id=f"ev-iso-{uuid4().hex[:6]}",
            title="Secret meeting",
            start_at=datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc)
            + timedelta(hours=10),
            end_at=datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc)
            + timedelta(hours=11),
            is_all_day=False,
        )
        db.add(event)
        await db.commit()

    intent = classify_query("what's on my calendar today")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, seed_user["workspace_id"], db)

    titles = [c.payload["title"] for c in envelope.cards]
    assert "Secret meeting" not in titles


# ---------------------------------------------------------------------------
# SQL injection safety
# ---------------------------------------------------------------------------


class TestSqlInjectionSafety:
    def test_contact_name_with_sql_chars(self):
        """Verify SQL special chars in contact name don't break the query."""
        intent = classify_query("find contact named Robert'); DROP TABLE contacts; --")
        assert intent is not None
        assert intent.intent_type == "contact_search"
        # The name is extracted as a string param, not interpolated into SQL
        assert "DROP TABLE" in intent.params["name"]

    def test_org_with_sql_chars(self):
        intent = classify_query("who works at Evil' OR '1'='1")
        assert intent is not None
        assert intent.intent_type == "contact_by_org"
        assert "OR" in intent.params["organization"]

    @pytest.mark.asyncio
    async def test_sql_injection_in_contact_search_returns_no_crash(
        self, test_session_factory, seed_user
    ):
        """Executing a search with SQL injection chars must not crash."""
        from api.services.query.router import route_deterministic

        intent = QueryIntent(
            intent_type="contact_search",
            params={"name": "'; DROP TABLE contacts; --"},
        )
        async with test_session_factory() as db:
            envelope = await route_deterministic(intent, seed_user["workspace_id"], db)

        # No crash, just empty results
        assert isinstance(envelope.cards, list)


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_endpoint_requires_auth(client, seed_user):
    ws_id = seed_user["workspace_id"]
    response = await client.post(
        "/api/v1/query",
        json={"query": "what's on my calendar today", "workspace_id": str(ws_id)},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_query_endpoint_rejects_wrong_workspace(client, auth_tokens):
    other_ws = uuid4()
    response = await client.post(
        "/api/v1/query",
        json={"query": "meetings today", "workspace_id": str(other_ws)},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_query_endpoint_pattern_match(client, auth_tokens):
    ws_id = auth_tokens["workspace_id"]
    response = await client.post(
        "/api/v1/query",
        json={"query": "what's on my calendar today", "workspace_id": str(ws_id)},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["confidence_level"] == "deterministic"
    assert data["metadata"]["query_path"] == "deterministic"


@pytest.mark.asyncio
async def test_query_endpoint_no_match_returns_fallback(client, auth_tokens):
    ws_id = auth_tokens["workspace_id"]
    response = await client.post(
        "/api/v1/query",
        json={"query": "explain quantum computing", "workspace_id": str(ws_id)},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer_text"] == "I don't understand that query yet."
    assert data["cards"] == []


@pytest.mark.asyncio
async def test_query_endpoint_returns_envelope_shape(client, auth_tokens):
    ws_id = auth_tokens["workspace_id"]
    response = await client.post(
        "/api/v1/query",
        json={"query": "events today", "workspace_id": str(ws_id)},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) >= {
        "answer_text",
        "confidence_level",
        "sources",
        "cards",
        "suggested_actions",
        "metadata",
    }
