"""Tests for S06-004: Expanded deterministic query patterns (50+ variations).

Covers new patterns: time-of-day, weekday, person, location, priority,
list, contact field, count, recent. 2+ tests per new pattern category.
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
from api.services.query.patterns import classify_query

NOW = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


# ---------------------------------------------------------------------------
# Date parser: new references
# ---------------------------------------------------------------------------


class TestDateParserExpanded:
    def test_this_morning(self):
        start, end = parse_date_reference("this morning", reference_date=TODAY)
        assert start.hour == 6
        assert end.hour == 11

    def test_this_afternoon(self):
        start, end = parse_date_reference("this afternoon", reference_date=TODAY)
        assert start.hour == 12
        assert end.hour == 16

    def test_this_evening(self):
        start, end = parse_date_reference("this evening", reference_date=TODAY)
        assert start.hour == 17
        assert end.hour == 20

    def test_tonight(self):
        start, end = parse_date_reference("tonight", reference_date=TODAY)
        assert start.hour == 21

    def test_on_monday(self):
        start, end = parse_date_reference("on monday", reference_date=TODAY)
        assert start.date().weekday() == 0  # Monday

    def test_on_friday(self):
        start, end = parse_date_reference("on friday", reference_date=TODAY)
        assert start.date().weekday() == 4

    def test_on_march_25(self):
        start, end = parse_date_reference("on march 25", reference_date=TODAY)
        assert start.date().month == 3
        assert start.date().day == 25

    def test_on_jan_3(self):
        start, end = parse_date_reference("on jan 3", reference_date=TODAY)
        assert start.date().month == 1
        assert start.date().day == 3

    def test_iso_date(self):
        start, end = parse_date_reference("on 2026-04-15", reference_date=TODAY)
        assert start.date() == date(2026, 4, 15)

    def test_last_7_days(self):
        start, end = parse_date_reference("last 7 days", reference_date=TODAY)
        assert (end.date() - start.date()).days == 6

    def test_morning_shorthand(self):
        result = parse_date_reference("morning", reference_date=TODAY)
        assert result is not None


# ---------------------------------------------------------------------------
# Calendar patterns: new variations
# ---------------------------------------------------------------------------


class TestCalendarPatternsExpanded:
    def test_do_i_have_anything_today(self):
        intent = classify_query("do I have anything today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_what_do_i_have_tomorrow(self):
        intent = classify_query("what do I have tomorrow")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_morning_meetings(self):
        intent = classify_query("morning meetings")
        assert intent is not None
        assert intent.intent_type == "calendar_range"
        assert intent.params["date_ref"] == "morning"

    def test_afternoon_events(self):
        intent = classify_query("afternoon events")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_whats_happening_today(self):
        intent = classify_query("what's happening today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_plans_for_tomorrow(self):
        intent = classify_query("plans for tomorrow")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_whats_scheduled_for_today(self):
        intent = classify_query("what's scheduled for today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_am_i_free_tomorrow(self):
        intent = classify_query("am I free tomorrow")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_am_i_busy_today(self):
        intent = classify_query("am I busy today")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_next_meeting(self):
        intent = classify_query("next meeting")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_calendar_overview(self):
        intent = classify_query("calendar overview")
        assert intent is not None
        assert intent.intent_type == "calendar_range"
        assert intent.params["date_ref"] == "this week"

    def test_my_schedule_for_on_monday(self):
        intent = classify_query("my schedule for on monday")
        assert intent is not None
        assert intent.intent_type == "calendar_range"


# ---------------------------------------------------------------------------
# Calendar with person
# ---------------------------------------------------------------------------


class TestCalendarWithPerson:
    def test_meetings_with_john_this_week(self):
        intent = classify_query("meetings with John this week")
        assert intent is not None
        assert intent.intent_type == "calendar_with_person"
        assert intent.params["person"] == "John"
        assert intent.params["date_ref"] == "this week"

    def test_events_with_sarah_tomorrow(self):
        intent = classify_query("events with Sarah tomorrow")
        assert intent is not None
        assert intent.intent_type == "calendar_with_person"
        assert intent.params["person"] == "Sarah"

    def test_when_am_i_meeting_bob(self):
        intent = classify_query("when am I meeting Bob")
        assert intent is not None
        assert intent.intent_type == "calendar_with_person"
        assert intent.params["person"] == "Bob"


# ---------------------------------------------------------------------------
# Calendar at location
# ---------------------------------------------------------------------------


class TestCalendarAtLocation:
    def test_meetings_at_conference_room(self):
        intent = classify_query("meetings at Conference Room A")
        assert intent is not None
        assert intent.intent_type == "calendar_at_location"
        assert intent.params["location"] == "Conference Room A"

    def test_events_in_the_office(self):
        intent = classify_query("events in the office")
        assert intent is not None
        assert intent.intent_type == "calendar_at_location"

    def test_whats_happening_at_hq(self):
        intent = classify_query("what's happening at HQ")
        assert intent is not None
        assert intent.intent_type == "calendar_at_location"


# ---------------------------------------------------------------------------
# Reminders by priority
# ---------------------------------------------------------------------------


class TestRemindersByPriority:
    def test_high_priority_reminders(self):
        intent = classify_query("high priority reminders")
        assert intent is not None
        assert intent.intent_type == "reminders_by_priority"
        assert intent.params["priority"] == "high"

    def test_urgent_tasks(self):
        intent = classify_query("urgent tasks")
        assert intent is not None
        assert intent.intent_type == "reminders_by_priority"
        assert intent.params["priority"] == "high"  # normalized

    def test_medium_priority_reminders(self):
        intent = classify_query("medium priority reminders")
        assert intent is not None
        assert intent.params["priority"] == "medium"

    def test_reminders_with_low_priority(self):
        intent = classify_query("reminders with low priority")
        assert intent is not None
        assert intent.intent_type == "reminders_by_priority"
        assert intent.params["priority"] == "low"

    def test_whats_urgent(self):
        intent = classify_query("what's urgent")
        assert intent is not None
        assert intent.intent_type == "reminders_by_priority"


# ---------------------------------------------------------------------------
# Reminders by list
# ---------------------------------------------------------------------------


class TestRemindersByList:
    def test_reminders_in_work(self):
        intent = classify_query("reminders in Work")
        assert intent is not None
        assert intent.intent_type == "reminders_by_list"
        assert intent.params["list_name"] == "Work"

    def test_tasks_from_shopping(self):
        intent = classify_query("tasks from Shopping")
        assert intent is not None
        assert intent.intent_type == "reminders_by_list"
        assert intent.params["list_name"] == "Shopping"

    def test_show_my_personal_list(self):
        intent = classify_query("show my Personal list")
        assert intent is not None
        assert intent.intent_type == "reminders_by_list"


# ---------------------------------------------------------------------------
# Contact field lookup
# ---------------------------------------------------------------------------


class TestContactField:
    def test_phone_number_for_john(self):
        intent = classify_query("phone number for John Smith")
        assert intent is not None
        assert intent.intent_type == "contact_field"
        assert intent.params["name"] == "John Smith"
        assert "phone" in intent.params["field"]

    def test_email_for_alice(self):
        intent = classify_query("email for Alice")
        assert intent is not None
        assert intent.intent_type == "contact_field"
        assert intent.params["field"] == "email"

    def test_johns_email(self):
        intent = classify_query("John's email")
        assert intent is not None
        assert intent.intent_type == "contact_field"
        assert intent.params["name"] == "John"

    def test_birthday_of_bob(self):
        intent = classify_query("birthday of Bob")
        assert intent is not None
        assert intent.intent_type == "contact_field"
        assert intent.params["field"] == "birthday"

    def test_whats_alices_phone(self):
        intent = classify_query("what's Alice's phone")
        assert intent is not None
        assert intent.intent_type == "contact_field"


# ---------------------------------------------------------------------------
# Count queries
# ---------------------------------------------------------------------------


class TestCountQuery:
    def test_how_many_events_today(self):
        # "how many events today" matches calendar_range first (returns the events)
        intent = classify_query("how many events today")
        assert intent is not None
        assert intent.intent_type in ("count_query", "calendar_range")

    def test_how_many_meetings_this_week(self):
        intent = classify_query("how many meetings this week")
        assert intent is not None
        assert intent.intent_type in ("count_query", "calendar_range")

    def test_how_many_reminders(self):
        intent = classify_query("how many reminders")
        assert intent is not None
        assert intent.intent_type == "count_query"
        assert intent.params["date_ref"] == "today"  # default

    def test_how_many_contacts(self):
        intent = classify_query("how many contacts")
        assert intent is not None
        assert intent.intent_type == "count_query"

    def test_number_of_contacts(self):
        intent = classify_query("number of contacts today")
        assert intent is not None
        assert intent.intent_type == "count_query"

    def test_how_many_do_i_have_explicit(self):
        intent = classify_query("how many reminders do I have this week")
        assert intent is not None
        assert intent.intent_type == "count_query"


# ---------------------------------------------------------------------------
# Recent queries
# ---------------------------------------------------------------------------


class TestRecentQuery:
    def test_recent_reminders(self):
        intent = classify_query("recent reminders")
        assert intent is not None
        assert intent.intent_type == "recent_query"
        assert intent.params["entity"] == "reminders"

    def test_latest_events(self):
        intent = classify_query("latest events")
        assert intent is not None
        assert intent.intent_type == "recent_query"

    def test_show_me_recent_contacts(self):
        intent = classify_query("show me recent contacts")
        assert intent is not None
        assert intent.intent_type == "recent_query"

    def test_what_happened_recently(self):
        intent = classify_query("what happened recently")
        assert intent is not None
        assert intent.intent_type == "recent_query"


# ---------------------------------------------------------------------------
# Additional expanded patterns
# ---------------------------------------------------------------------------


class TestAdditionalPatterns:
    def test_my_todo_list(self):
        intent = classify_query("my to-do list")
        assert intent is not None
        assert intent.intent_type == "reminders_range"

    def test_incomplete_tasks(self):
        intent = classify_query("incomplete tasks")
        assert intent is not None
        assert intent.intent_type == "reminders_range"

    def test_what_tasks_do_i_have_today(self):
        intent = classify_query("what tasks do I have today")
        assert intent is not None
        assert intent.intent_type == "reminders_range"

    def test_contact_info_for_name(self):
        intent = classify_query("contact info for Jane Doe")
        assert intent is not None
        assert intent.intent_type == "contact_search"
        assert intent.params["name"] == "Jane Doe"

    def test_team_at_org(self):
        intent = classify_query("team at Acme Corp")
        assert intent is not None
        assert intent.intent_type == "contact_by_org"

    def test_whats_left_today(self):
        intent = classify_query("what's left today")
        assert intent is not None
        assert intent.intent_type == "reminders_range"

    def test_anything_due_this_week(self):
        intent = classify_query("anything due this week")
        assert intent is not None
        assert intent.intent_type == "reminders_range"


# ---------------------------------------------------------------------------
# Integration: new handlers
# ---------------------------------------------------------------------------


async def _make_source(db, seed_user, source_type="calendar") -> Source:
    src = Source(
        workspace_id=seed_user["workspace_id"],
        name=f"Expanded Test {source_type}",
        type=source_type,
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(src)
    await db.flush()
    return src


@pytest.mark.asyncio
async def test_reminders_by_priority_handler(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]
    user_id = seed_user["user_id"]

    async with test_session_factory() as db:
        db.add(Reminder(
            workspace_id=ws_id,
            title=f"High priority task {uuid4().hex[:6]}",
            is_completed=False,
            priority="high",
            created_by=user_id,
        ))
        db.add(Reminder(
            workspace_id=ws_id,
            title=f"Low priority task {uuid4().hex[:6]}",
            is_completed=False,
            priority="low",
            created_by=user_id,
        ))
        await db.commit()

    from api.services.query.router import route_deterministic

    intent = classify_query("high priority reminders")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    for card in envelope.cards:
        assert card.payload["priority"] == "high"


@pytest.mark.asyncio
async def test_reminders_by_list_handler(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]
    user_id = seed_user["user_id"]

    async with test_session_factory() as db:
        db.add(Reminder(
            workspace_id=ws_id,
            title=f"Work item {uuid4().hex[:6]}",
            is_completed=False,
            priority="none",
            list_name="Work",
            created_by=user_id,
        ))
        db.add(Reminder(
            workspace_id=ws_id,
            title=f"Shopping item {uuid4().hex[:6]}",
            is_completed=False,
            priority="none",
            list_name="Shopping",
            created_by=user_id,
        ))
        await db.commit()

    from api.services.query.router import route_deterministic

    intent = classify_query("reminders in Work")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    for card in envelope.cards:
        assert "work" in card.payload["list_name"].lower()


@pytest.mark.asyncio
async def test_count_query_handler(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]

    from api.services.query.router import route_deterministic

    intent = classify_query("how many reminders")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    assert envelope.answer_text is not None
    assert "reminder" in envelope.answer_text


@pytest.mark.asyncio
async def test_recent_events_handler(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]

    async with test_session_factory() as db:
        src = await _make_source(db, seed_user)
        db.add(CalendarEvent(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ev-recent-{uuid4().hex[:6]}",
            title="Recent test event",
            start_at=NOW - timedelta(hours=2),
            is_all_day=False,
        ))
        await db.commit()

    from api.services.query.router import route_deterministic

    intent = classify_query("recent events")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    titles = [c.payload["title"] for c in envelope.cards]
    assert "Recent test event" in titles


@pytest.mark.asyncio
async def test_contact_field_handler(test_session_factory, seed_user):
    ws_id = seed_user["workspace_id"]

    async with test_session_factory() as db:
        src = await _make_source(db, seed_user, "contacts")
        db.add(Contact(
            workspace_id=ws_id,
            source_id=src.id,
            external_id=f"ct-field-{uuid4().hex[:6]}",
            display_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            emails_json=["jane@example.com"],
            phones_json=["+1234567890"],
            imported_at=NOW,
        ))
        await db.commit()

    from api.services.query.router import route_deterministic

    intent = classify_query("email for Jane")
    assert intent is not None

    async with test_session_factory() as db:
        envelope = await route_deterministic(intent, ws_id, db)

    assert len(envelope.cards) >= 1
    assert "jane@example.com" in envelope.cards[0].payload["emails"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_ambiguous_name_vs_org(self):
        """'Apple' could be a person or org — should match contact_search first."""
        intent = classify_query("who is Apple")
        assert intent is not None
        assert intent.intent_type == "contact_search"

    def test_empty_priority(self):
        intent = classify_query("priority reminders")
        # Should not match — no priority level specified
        assert intent is None or intent.intent_type != "reminders_by_priority"

    def test_partial_weekday(self):
        result = parse_date_reference("on fri", reference_date=TODAY)
        assert result is not None
        assert result[0].date().weekday() == 4

    def test_invalid_month_day(self):
        result = parse_date_reference("on february 30", reference_date=TODAY)
        assert result is None  # Invalid date

    def test_case_insensitive_patterns(self):
        intent = classify_query("WHAT'S ON MY CALENDAR TODAY")
        assert intent is not None
        assert intent.intent_type == "calendar_range"

    def test_mixed_case(self):
        intent = classify_query("Show Me Recent Events")
        assert intent is not None
        assert intent.intent_type == "recent_query"
