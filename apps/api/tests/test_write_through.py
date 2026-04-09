"""Tests for S05-003: Write-through reminder creation.

Covers:
  - Create reminder returns 201 with pending status
  - Background task updates status to success
  - Rate limit enforced (10/min)
  - Validation errors (missing title, bad priority)
  - Auth and CSRF required
  - Audit log created
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from api.db.models.reminder import Reminder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers(auth_tokens: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {auth_tokens['access_token']}",
        "X-CSRF-Token": auth_tokens["csrf_token"],
    }


def _csrf_cookies(auth_tokens: dict) -> dict[str, str]:
    return {"ekamcore_csrf": auth_tokens["csrf_token"]}


def _valid_body() -> dict:
    return {
        "title": f"Test reminder {uuid4().hex[:6]}",
        "due_at": "2026-04-15T09:00:00Z",
        "priority": "medium",
        "list_name": "Work",
        "notes": "Don't forget",
    }


def _mock_redis():
    """Return a mock Redis that allows rate limiting to pass."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.ttl = AsyncMock(return_value=60)
    pipe_mock = AsyncMock()
    pipe_mock.incr = AsyncMock()
    pipe_mock.expire = AsyncMock()
    pipe_mock.execute = AsyncMock(return_value=[1, True])
    mock.pipeline = lambda transaction=True: pipe_mock
    return mock


# ---------------------------------------------------------------------------
# Creation tests
# ---------------------------------------------------------------------------


class TestCreateReminder:
    @pytest.mark.asyncio
    async def test_creates_reminder_with_pending_status(
        self, client: AsyncClient, auth_tokens: dict
    ):
        body = _valid_body()
        with patch(
            "api.routers.reminders.get_redis", return_value=_mock_redis()
        ), patch(
            "api.routers.reminders.send_to_apple_reminders"
        ):
            response = await client.post(
                "/api/v1/reminders",
                json=body,
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == body["title"]
        assert data["write_through_status"] == "pending"
        assert data["priority"] == "medium"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_returns_correct_fields(
        self, client: AsyncClient, auth_tokens: dict
    ):
        body = _valid_body()
        with patch(
            "api.routers.reminders.get_redis", return_value=_mock_redis()
        ), patch(
            "api.routers.reminders.send_to_apple_reminders"
        ):
            response = await client.post(
                "/api/v1/reminders",
                json=body,
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["due_at"] is not None
        assert data["list_name"] == "Work"
        assert data["notes"] == "Don't forget"
        assert data["is_completed"] is False

    @pytest.mark.asyncio
    async def test_minimal_body_title_only(
        self, client: AsyncClient, auth_tokens: dict
    ):
        with patch(
            "api.routers.reminders.get_redis", return_value=_mock_redis()
        ), patch(
            "api.routers.reminders.send_to_apple_reminders"
        ):
            response = await client.post(
                "/api/v1/reminders",
                json={"title": "Just a title"},
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Just a title"
        assert data["priority"] == "none"
        assert data["due_at"] is None


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


class TestWriteThroughBackground:
    @pytest.mark.asyncio
    async def test_background_task_updates_status(self, test_session_factory, seed_user):
        """Simulate the background task updating write_through_status."""
        from api.services.write_through import send_to_apple_reminders

        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            reminder = Reminder(
                workspace_id=ws_id,
                title=f"BG task test {uuid4().hex[:6]}",
                is_completed=False,
                priority="none",
                write_through_status="pending",
                created_by=user_id,
            )
            db.add(reminder)
            await db.commit()
            reminder_id = reminder.id

        # Run background task
        await send_to_apple_reminders(reminder_id)

        # Verify status updated
        from sqlalchemy import select

        async with test_session_factory() as db:
            result = await db.execute(
                select(Reminder).where(Reminder.id == reminder_id)
            )
            updated = result.scalar_one()
            assert updated.write_through_status == "success"
            assert updated.external_id is not None
            assert updated.external_id.startswith("stub-eventkit-")

    @pytest.mark.asyncio
    async def test_background_task_marks_failed_after_retries(
        self, test_session_factory, seed_user
    ):
        """If the manager API always fails, status should be 'failed'."""
        from api.services.write_through import send_to_apple_reminders

        ws_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            reminder = Reminder(
                workspace_id=ws_id,
                title=f"Fail test {uuid4().hex[:6]}",
                is_completed=False,
                priority="none",
                write_through_status="pending",
                created_by=user_id,
            )
            db.add(reminder)
            await db.commit()
            reminder_id = reminder.id

        with patch(
            "api.services.write_through._call_manager_api",
            side_effect=Exception("Manager unavailable"),
        ), patch(
            "api.services.write_through._RETRY_DELAY_SECS", 0  # Skip delays in test
        ):
            await send_to_apple_reminders(reminder_id)

        from sqlalchemy import select

        async with test_session_factory() as db:
            result = await db.execute(
                select(Reminder).where(Reminder.id == reminder_id)
            )
            updated = result.scalar_one()
            assert updated.write_through_status == "failed"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(
        self, client: AsyncClient, auth_tokens: dict
    ):
        """After hitting rate limit, should return 429."""
        rate_limited_redis = _mock_redis()
        rate_limited_redis.get = AsyncMock(return_value="10")  # At the limit

        with patch(
            "api.routers.reminders.get_redis", return_value=rate_limited_redis
        ):
            response = await client.post(
                "/api/v1/reminders",
                json=_valid_body(),
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 429
        data = response.json()
        assert data["error_code"] == "RATE_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_title_returns_422(
        self, client: AsyncClient, auth_tokens: dict
    ):
        with patch(
            "api.routers.reminders.get_redis", return_value=_mock_redis()
        ):
            response = await client.post(
                "/api/v1/reminders",
                json={"priority": "high"},
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_title_returns_422(
        self, client: AsyncClient, auth_tokens: dict
    ):
        with patch(
            "api.routers.reminders.get_redis", return_value=_mock_redis()
        ):
            response = await client.post(
                "/api/v1/reminders",
                json={"title": ""},
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_priority_returns_422(
        self, client: AsyncClient, auth_tokens: dict
    ):
        with patch(
            "api.routers.reminders.get_redis", return_value=_mock_redis()
        ):
            response = await client.post(
                "/api/v1/reminders",
                json={"title": "Test", "priority": "critical"},
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Auth / CSRF
# ---------------------------------------------------------------------------


class TestAuthAndCsrf:
    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient):
        """Without auth or CSRF, expect 401 or 403 (CSRF dependency runs first)."""
        response = await client.post(
            "/api/v1/reminders",
            json=_valid_body(),
        )
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_requires_csrf(self, client: AsyncClient, auth_tokens: dict):
        """POST without CSRF header should fail."""
        response = await client.post(
            "/api/v1/reminders",
            json=_valid_body(),
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            cookies=_csrf_cookies(auth_tokens),
        )
        # Missing X-CSRF-Token header → 403
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_reminder_created_audit_event(
        self, client: AsyncClient, auth_tokens: dict, test_session_factory
    ):
        with patch(
            "api.routers.reminders.get_redis", return_value=_mock_redis()
        ), patch(
            "api.routers.reminders.send_to_apple_reminders"
        ):
            response = await client.post(
                "/api/v1/reminders",
                json=_valid_body(),
                headers=_auth_headers(auth_tokens),
                cookies=_csrf_cookies(auth_tokens),
            )

        assert response.status_code == 201

        # Verify audit log entry
        from sqlalchemy import select
        from api.db.models.audit_log import AuditLog

        async with test_session_factory() as db:
            result = await db.execute(
                select(AuditLog)
                .where(AuditLog.action == "reminder_created")
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
            entry = result.scalar_one_or_none()

        assert entry is not None
        assert entry.object_type == "reminder"
        assert str(entry.user_id) == str(auth_tokens["user_id"])
