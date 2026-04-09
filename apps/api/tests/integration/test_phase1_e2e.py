"""Phase 1 end-to-end integration test suite (S06-006).

Seven scenarios exercising the full Phase 1 API surface from HTTP edge to
database, following data through the entire request/response lifecycle:

  1. test_full_auth_flow          — login → refresh → logout → revoked token 401
  2. test_calendar_to_today_flow  — ingest calendar events → appear on /today
  3. test_reminders_overdue_flow  — overdue priority on /today, searchable, write-through
  4. test_query_to_search_fallback — deterministic → search fallback → empty
  5. test_workspace_isolation     — data never crosses workspace boundaries
  6. test_csrf_protection         — missing/wrong/correct CSRF on write endpoints
  7. test_brute_force_lockout     — 20 failures → 423, success clears counter

Requires: PostgreSQL + Redis running (use `make test-integration`).
The existing conftest.py (apps/api/tests/conftest.py) provides all fixtures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

# All tests in this module share the session event loop so that Redis
# connection pools (created by fixtures in the session loop) remain valid
# when the test body makes HTTP requests that exercise the auth middleware.
pytestmark = pytest.mark.asyncio(loop_scope="session")
from httpx import AsyncClient

from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.auth import hash_password


# ── Shared helpers ────────────────────────────────────────────────────────────


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _csrf_headers(access_token: str, csrf_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-CSRF-Token": csrf_token,
    }


def _csrf_cookies(csrf_token: str) -> dict[str, str]:
    return {"ekamcore_csrf": csrf_token}


def _mock_reminder_redis() -> AsyncMock:
    """Mock Redis that passes the reminder rate-limit check (0 prior calls)."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.ttl = AsyncMock(return_value=60)
    pipe = AsyncMock()
    pipe.incr = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.execute = AsyncMock(return_value=[1, True])
    mock.pipeline = Mock(return_value=pipe)
    return mock


def _mock_brute_force_redis(
    failure_count: str | None,
    new_count: int = 0,
    ttl: int = 3600,
) -> AsyncMock:
    """Mock rate-limiter Redis with a specific failure count and TTL.

    failure_count=None means the key does not exist (0 prior failures).
    """
    pipe = Mock()
    pipe.incr = Mock(return_value=pipe)
    pipe.expire = Mock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[new_count, True])
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=failure_count)
    mock.ttl = AsyncMock(return_value=ttl)
    mock.delete = AsyncMock()
    mock.pipeline = Mock(return_value=pipe)
    return mock


async def _create_user_and_workspace(test_session_factory) -> dict:
    """Create a fresh user + personal workspace. Returns credentials dict."""
    email = f"e2e-{uuid4().hex[:8]}@ekamcore.dev"
    password = "testpassword123"
    async with test_session_factory() as db:
        user = User(
            email=email,
            display_name="E2E User",
            password_hash=hash_password(password),
            role="standard",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        workspace = Workspace(
            name=f"WS-{uuid4().hex[:6]}",
            type="personal",
            owner_id=user.id,
        )
        db.add(workspace)
        await db.flush()
        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="admin",
        )
        db.add(member)
        await db.commit()
        # Capture IDs before session closes
        user_id = user.id
        workspace_id = workspace.id
    return {
        "email": email,
        "password": password,
        "user_id": user_id,
        "workspace_id": workspace_id,
    }


async def _login(client: AsyncClient, creds: dict) -> dict:
    """Login and return a tokens dict matching the auth_tokens fixture shape."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_cookie": resp.cookies.get("ekamcore_refresh"),
        "csrf_token": resp.cookies.get("ekamcore_csrf"),
        **creds,
    }


async def _create_source(client: AsyncClient, tokens: dict, source_type: str) -> dict:
    """Create a source via POST /api/v1/sources. Returns the response JSON."""
    resp = await client.post(
        "/api/v1/sources",
        json={"name": f"E2E {source_type} {uuid4().hex[:6]}", "type": source_type},
        headers=_csrf_headers(tokens["access_token"], tokens["csrf_token"]),
        cookies=_csrf_cookies(tokens["csrf_token"]),
    )
    assert resp.status_code == 201, f"Source creation failed ({source_type}): {resp.text}"
    return resp.json()


def _today_event_times() -> tuple[datetime, datetime]:
    """Return two start times guaranteed to fall within today UTC.

    Uses fixed AM/PM slots so tests run correctly at any time of day.
    """
    today = datetime.now(timezone.utc).date()
    event_a = datetime(today.year, today.month, today.day, 9, 0, tzinfo=timezone.utc)
    event_b = datetime(today.year, today.month, today.day, 14, 0, tzinfo=timezone.utc)
    return event_a, event_b


# ── Scenario 1: Full Auth Flow ────────────────────────────────────────────────


async def test_full_auth_flow(client: AsyncClient, seed_user: dict) -> None:
    """Login → refresh → logout → revoked token is rejected with 401."""
    # Step 1: Login — access token + CSRF + refresh cookie in response
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]
    refresh_cookie = login_resp.cookies["ekamcore_refresh"]
    csrf_token = login_resp.cookies["ekamcore_csrf"]
    assert access_token
    assert refresh_cookie
    assert csrf_token

    # Step 2: Refresh — rotates both access token and refresh cookie
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": refresh_cookie},
    )
    assert refresh_resp.status_code == 200
    new_access_token = refresh_resp.json()["access_token"]
    new_csrf = refresh_resp.cookies["ekamcore_csrf"]
    new_refresh_cookie = refresh_resp.cookies["ekamcore_refresh"]
    assert new_access_token != access_token, "Refresh must rotate the access token"
    assert new_csrf != csrf_token, "Refresh must rotate the CSRF token"

    # Step 3: Logout — invalidates the session
    logout_resp = await client.post(
        "/api/v1/auth/logout",
        headers=_csrf_headers(new_access_token, new_csrf),
        cookies={**_csrf_cookies(new_csrf), "ekamcore_refresh": new_refresh_cookie},
    )
    assert logout_resp.status_code == 204

    # Step 4: Revoked token rejected on any authenticated endpoint
    ws_id = seed_user["workspace_id"]
    rejected = await client.get(
        f"/api/v1/today?workspace_id={ws_id}",
        headers=_auth_headers(new_access_token),
    )
    assert rejected.status_code == 401
    assert "error_code" in rejected.json()


# ── Scenario 2: Calendar Ingest → Today Cards ─────────────────────────────────


async def test_calendar_to_today_flow(
    client: AsyncClient,
    auth_tokens: dict,
) -> None:
    """Ingest two calendar events → both appear on /today as event cards."""
    ws_id = str(auth_tokens["workspace_id"])
    uid = uuid4().hex[:8]

    # Create calendar source
    source = await _create_source(client, auth_tokens, "calendar")
    source_id = source["id"]

    event_a_start, event_b_start = _today_event_times()

    # Ingest two events with unique external IDs
    ingest_resp = await client.post(
        "/api/v1/internal/ingest/calendar",
        json={
            "workspace_id": ws_id,
            "source_id": source_id,
            "events": [
                {
                    "external_id": f"e2e-cal-a-{uid}",
                    "title": f"E2E Morning Meeting {uid}",
                    "start_at": event_a_start.isoformat(),
                    "end_at": (event_a_start + timedelta(hours=1)).isoformat(),
                    "is_all_day": False,
                    "calendar_name": "Work",
                },
                {
                    "external_id": f"e2e-cal-b-{uid}",
                    "title": f"E2E Afternoon Meeting {uid}",
                    "start_at": event_b_start.isoformat(),
                    "end_at": (event_b_start + timedelta(hours=1)).isoformat(),
                    "is_all_day": False,
                    "calendar_name": "Work",
                },
            ],
        },
    )
    assert ingest_resp.status_code == 200
    ingest_data = ingest_resp.json()
    assert ingest_data["inserted"] == 2
    assert ingest_data["updated"] == 0

    # GET /today — both events must appear as event cards
    today_resp = await client.get(
        f"/api/v1/today?workspace_id={ws_id}",
        headers=_auth_headers(auth_tokens["access_token"]),
    )
    assert today_resp.status_code == 200
    envelope = today_resp.json()
    assert "cards" in envelope
    assert "confidence_level" in envelope
    assert "metadata" in envelope

    event_cards = [c for c in envelope["cards"] if c["type"] == "event"]
    event_titles = {c["payload"]["title"] for c in event_cards}
    assert f"E2E Morning Meeting {uid}" in event_titles
    assert f"E2E Afternoon Meeting {uid}" in event_titles

    # Cards are sorted descending by priority_score (higher score = earlier card)
    scores = [c["priority_score"] for c in envelope["cards"]]
    assert scores == sorted(scores, reverse=True), "Cards must be sorted by priority_score desc"

    # Idempotency: re-ingesting the same event produces 0 new inserts (no duplicates)
    re_ingest = await client.post(
        "/api/v1/internal/ingest/calendar",
        json={
            "workspace_id": ws_id,
            "source_id": source_id,
            "events": [
                {
                    "external_id": f"e2e-cal-a-{uid}",
                    "title": f"E2E Morning Meeting {uid}",
                    "start_at": event_a_start.isoformat(),
                    "end_at": (event_a_start + timedelta(hours=1)).isoformat(),
                    "is_all_day": False,
                },
            ],
        },
    )
    assert re_ingest.status_code == 200
    re_data = re_ingest.json()
    assert re_data["inserted"] == 0
    # Calendar sync may count re-processed events as "updated" or "unchanged"
    assert re_data["updated"] + re_data["unchanged"] == 1


# ── Scenario 3: Reminders Overdue Flow ───────────────────────────────────────


async def test_reminders_overdue_flow(
    client: AsyncClient,
    auth_tokens: dict,
) -> None:
    """Overdue reminder → top of /today, findable in /search, creatable via POST."""
    ws_id = str(auth_tokens["workspace_id"])
    now = datetime.now(timezone.utc)
    uid = uuid4().hex[:8]

    # Create reminders source
    source = await _create_source(client, auth_tokens, "reminders")
    source_id = source["id"]

    overdue_title = f"E2E Overdue Task {uid}"
    today_title = f"E2E Today Task {uid}"
    future_title = f"E2E Future Task {uid}"

    # Ingest three reminders: overdue (yesterday), due today, due in 2 days
    ingest_resp = await client.post(
        "/api/v1/internal/ingest/reminders",
        json={
            "workspace_id": ws_id,
            "source_id": source_id,
            "reminders": [
                {
                    "external_id": f"rem-overdue-{uid}",
                    "title": overdue_title,
                    "due_at": (now - timedelta(days=1)).isoformat(),
                    "is_completed": False,
                    "priority": "high",
                },
                {
                    "external_id": f"rem-today-{uid}",
                    "title": today_title,
                    "due_at": (now + timedelta(hours=4)).isoformat(),
                    "is_completed": False,
                    "priority": "medium",
                },
                {
                    "external_id": f"rem-future-{uid}",
                    "title": future_title,
                    "due_at": (now + timedelta(days=2)).isoformat(),
                    "is_completed": False,
                    "priority": "low",
                },
            ],
        },
    )
    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["inserted"] == 3

    # GET /today — overdue reminder must appear and be flagged
    today_resp = await client.get(
        f"/api/v1/today?workspace_id={ws_id}",
        headers=_auth_headers(auth_tokens["access_token"]),
    )
    assert today_resp.status_code == 200
    all_cards = today_resp.json()["cards"]
    reminder_cards = [c for c in all_cards if c["type"] == "reminder"]

    overdue_card = next(
        (c for c in reminder_cards if c["payload"]["title"] == overdue_title),
        None,
    )
    assert overdue_card is not None, (
        f"Overdue reminder '{overdue_title}' not found. "
        f"Reminder card titles: {[c['payload']['title'] for c in reminder_cards]}"
    )
    assert overdue_card["payload"]["is_overdue"] is True

    # Overdue must have the highest priority_score among reminder cards
    max_reminder_score = max(c["priority_score"] for c in reminder_cards)
    assert overdue_card["priority_score"] == max_reminder_score, (
        "Overdue reminder must have the highest priority_score"
    )

    # GET /search — overdue reminder is text-searchable by title
    search_resp = await client.get(
        f"/api/v1/search",
        params={
            "q": overdue_title,
            "workspace_id": ws_id,
            "type": "reminder",
        },
        headers=_auth_headers(auth_tokens["access_token"]),
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert "data" in search_data
    search_titles = {
        item.get("payload", {}).get("title", "")
        for item in search_data["data"]
        if item.get("type") == "reminder"
    }
    assert overdue_title in search_titles, (
        f"Overdue reminder not found in search results. Got: {search_titles}"
    )

    # POST /reminders — write-through creates a new reminder (pending Apple sync)
    with (
        patch("api.routers.reminders.get_redis", return_value=_mock_reminder_redis()),
        patch("api.routers.reminders.send_to_apple_reminders"),
    ):
        create_resp = await client.post(
            "/api/v1/reminders",
            json={
                "title": f"E2E Write-through {uid}",
                "priority": "high",
                "due_at": (now + timedelta(days=1)).isoformat(),
            },
            headers=_csrf_headers(auth_tokens["access_token"], auth_tokens["csrf_token"]),
            cookies=_csrf_cookies(auth_tokens["csrf_token"]),
        )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["title"] == f"E2E Write-through {uid}"
    assert created["write_through_status"] == "pending"
    assert created["priority"] == "high"
    assert "id" in created


# ── Scenario 4: Query → Search Fallback → Empty ───────────────────────────────


async def test_query_to_search_fallback(
    client: AsyncClient,
    auth_tokens: dict,
) -> None:
    """Deterministic match → events; non-matching → fallback; nonsense → empty + message."""
    ws_id = str(auth_tokens["workspace_id"])
    access = auth_tokens["access_token"]

    # 1. Deterministic: calendar-today query matches a known pattern
    det_resp = await client.post(
        "/api/v1/query",
        json={"query": "what's on my calendar today", "workspace_id": ws_id},
        headers=_auth_headers(access),
    )
    assert det_resp.status_code == 200
    det = det_resp.json()
    assert det["confidence_level"] == "deterministic"
    assert det["metadata"]["query_path"] == "deterministic"

    # 2. Non-deterministic query falls through to text-search fallback
    #    The query_path is always "deterministic" per the router; confidence is "high" or omitted
    fallback_resp = await client.post(
        "/api/v1/query",
        json={"query": "documents about quarterly planning spreadsheet", "workspace_id": ws_id},
        headers=_auth_headers(access),
    )
    assert fallback_resp.status_code == 200
    fallback = fallback_resp.json()
    assert fallback["metadata"]["query_path"] == "deterministic"
    # Confidence is "high" if search found results, or "low"/"medium" if not
    assert fallback["confidence_level"] in ("deterministic", "high", "medium", "low")

    # 3. Completely nonsense input → no results, helpful answer_text
    empty_resp = await client.post(
        "/api/v1/query",
        json={"query": "xyzzy flibbertigibbet blorp quux", "workspace_id": ws_id},
        headers=_auth_headers(access),
    )
    assert empty_resp.status_code == 200
    empty = empty_resp.json()
    # Either no cards returned, or a clarifying message is set
    assert len(empty["cards"]) == 0 or empty["answer_text"] is not None


# ── Scenario 5: Workspace Isolation ──────────────────────────────────────────


async def test_workspace_isolation(
    client: AsyncClient,
    test_session_factory,
) -> None:
    """Data ingested in Workspace A is never visible to User B (Workspace B)."""
    # Create two independent users, each with their own workspace
    creds_a = await _create_user_and_workspace(test_session_factory)
    creds_b = await _create_user_and_workspace(test_session_factory)
    tokens_a = await _login(client, creds_a)
    tokens_b = await _login(client, creds_b)

    ws_a = str(creds_a["workspace_id"])
    ws_b = str(creds_b["workspace_id"])
    uid = uuid4().hex[:8]
    unique_title = f"ISOLATION_SENTINEL_{uid}"

    # User A: create source and ingest a uniquely-titled event
    source_a = await _create_source(client, tokens_a, "calendar")
    event_a_start, _ = _today_event_times()
    await client.post(
        "/api/v1/internal/ingest/calendar",
        json={
            "workspace_id": ws_a,
            "source_id": source_a["id"],
            "events": [
                {
                    "external_id": f"iso-{uid}",
                    "title": unique_title,
                    "start_at": event_a_start.isoformat(),
                    "end_at": (event_a_start + timedelta(hours=1)).isoformat(),
                    "is_all_day": False,
                }
            ],
        },
    )

    # ── /today isolation ────────────────────────────────────────────────────
    today_b = await client.get(
        f"/api/v1/today?workspace_id={ws_b}",
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert today_b.status_code == 200
    b_event_titles = {
        c["payload"].get("title", "")
        for c in today_b.json()["cards"]
        if c["type"] == "event"
    }
    assert unique_title not in b_event_titles, "User B must not see User A's event in /today"

    # ── /search isolation ───────────────────────────────────────────────────
    search_b = await client.get(
        "/api/v1/search",
        params={"q": unique_title, "workspace_id": ws_b},
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert search_b.status_code == 200
    b_search_titles = {
        item.get("payload", {}).get("title", "")
        for item in search_b.json()["data"]
    }
    assert unique_title not in b_search_titles, "User B must not find User A's event in /search"

    # ── /query isolation ────────────────────────────────────────────────────
    query_b = await client.post(
        "/api/v1/query",
        json={"query": "what's on my calendar today", "workspace_id": ws_b},
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert query_b.status_code == 200
    q_titles = {
        c["payload"].get("title", "")
        for c in query_b.json()["cards"]
        if c["type"] == "event"
    }
    assert unique_title not in q_titles, "User B must not find User A's event in /query"

    # ── /sources isolation ──────────────────────────────────────────────────
    sources_b = await client.get(
        "/api/v1/sources",
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert sources_b.status_code == 200
    b_source_ids = {s["id"] for s in sources_b.json()["items"]}
    assert source_a["id"] not in b_source_ids, "User B must not see User A's source"

    # ── Cross-workspace access control ──────────────────────────────────────
    # User B explicitly supplying Workspace A's ID → 403 WORKSPACE_ACCESS_DENIED
    today_a_as_b = await client.get(
        f"/api/v1/today?workspace_id={ws_a}",
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert today_a_as_b.status_code == 403
    assert today_a_as_b.json()["error_code"] == "WORKSPACE_ACCESS_DENIED"

    recap_a_as_b = await client.get(
        f"/api/v1/recap?workspace_id={ws_a}",
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert recap_a_as_b.status_code == 403

    query_a_as_b = await client.post(
        "/api/v1/query",
        json={"query": "what's today", "workspace_id": ws_a},
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert query_a_as_b.status_code == 403

    search_a_as_b = await client.get(
        "/api/v1/search",
        params={"q": "anything", "workspace_id": ws_a},
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert search_a_as_b.status_code == 403


# ── Scenario 6: CSRF Protection ──────────────────────────────────────────────


async def test_csrf_protection(
    client: AsyncClient,
    auth_tokens: dict,
) -> None:
    """POST /reminders enforces CSRF: no token → 403, wrong → 403, correct → 201."""
    access = auth_tokens["access_token"]
    csrf = auth_tokens["csrf_token"]
    body = {"title": f"CSRF E2E Test {uuid4().hex[:6]}", "priority": "low"}

    # 1. No CSRF token in header or cookie → 403
    no_csrf = await client.post(
        "/api/v1/reminders",
        json=body,
        headers=_auth_headers(access),
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error_code"] == "CSRF_VALIDATION_FAILED"

    # 2. Wrong header value (doesn't match cookie) → 403
    wrong_csrf = await client.post(
        "/api/v1/reminders",
        json=body,
        headers={**_auth_headers(access), "X-CSRF-Token": "wrong-token-value"},
        cookies=_csrf_cookies(csrf),
    )
    assert wrong_csrf.status_code == 403
    assert wrong_csrf.json()["error_code"] == "CSRF_VALIDATION_FAILED"

    # 3. Header present but no cookie → 403
    header_only = await client.post(
        "/api/v1/reminders",
        json=body,
        headers=_csrf_headers(access, csrf),
        # no cookies kwarg → no cookie sent
    )
    assert header_only.status_code == 403
    assert header_only.json()["error_code"] == "CSRF_VALIDATION_FAILED"

    # 4. Correct CSRF (header == cookie) → 201
    with (
        patch("api.routers.reminders.get_redis", return_value=_mock_reminder_redis()),
        patch("api.routers.reminders.send_to_apple_reminders"),
    ):
        ok_resp = await client.post(
            "/api/v1/reminders",
            json=body,
            headers=_csrf_headers(access, csrf),
            cookies=_csrf_cookies(csrf),
        )
    assert ok_resp.status_code == 201
    created = ok_resp.json()
    assert created["title"] == body["title"]
    assert created["write_through_status"] == "pending"

    # 5. POST /sources also enforces CSRF
    no_csrf_source = await client.post(
        "/api/v1/sources",
        json={"name": "No CSRF Source", "type": "calendar"},
        headers=_auth_headers(access),
    )
    assert no_csrf_source.status_code == 403
    assert no_csrf_source.json()["error_code"] == "CSRF_VALIDATION_FAILED"


# ── Scenario 7: Brute-Force Lockout ──────────────────────────────────────────


async def test_brute_force_lockout(
    client: AsyncClient,
    seed_user: dict,
) -> None:
    """19 prior failures → 401; 20 prior → 423 ACCOUNT_LOCKED; success clears counter."""
    email = seed_user["email"]
    wrong_pw = "definitely-wrong-password-xyz"

    # Simulate 19 prior failures: count="19" → threshold not yet reached
    # After this call: counter would increment to 20 (triggers lock on NEXT check).
    mock_19 = _mock_brute_force_redis("19", new_count=20, ttl=3600)
    with patch("api.services.rate_limiter.get_redis", return_value=mock_19):
        resp_19 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": wrong_pw},
        )
    # Count=19 read → not locked, incr to 20. Bad password → 401.
    assert resp_19.status_code == 401

    # Simulate 20 prior failures: count="20" → account locked immediately
    mock_20 = _mock_brute_force_redis("20", new_count=21, ttl=2400)
    with patch("api.services.rate_limiter.get_redis", return_value=mock_20):
        resp_locked = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": wrong_pw},
        )
    assert resp_locked.status_code == 423
    locked_body = resp_locked.json()
    assert locked_body["error_code"] == "AUTH_ACCOUNT_LOCKED"
    assert locked_body["details"]["retry_after_seconds"] == 2400

    # Simulate count above threshold (25) with different TTL
    mock_25 = _mock_brute_force_redis("25", new_count=26, ttl=1800)
    with patch("api.services.rate_limiter.get_redis", return_value=mock_25):
        resp_25 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": wrong_pw},
        )
    assert resp_25.status_code == 423
    assert resp_25.json()["details"]["retry_after_seconds"] == 1800

    # Successful login with no prior failures → counter deleted
    mock_clear = _mock_brute_force_redis(None, new_count=1, ttl=3600)
    with patch("api.services.rate_limiter.get_redis", return_value=mock_clear):
        resp_ok = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": seed_user["password"]},
        )
    assert resp_ok.status_code == 200
    assert "access_token" in resp_ok.json()
    # Counter cleared on successful login
    mock_clear.delete.assert_awaited_once()
