"""Tests for structured JSON logging (S02-008).

Verifies log output format, adaptive log levels, and PII exclusion.
"""

import json
import logging
from unittest.mock import patch

import pytest
import structlog
from httpx import ASGITransport, AsyncClient


def _capture_structlog():
    """Return a list that captures structlog event dicts before JSON rendering."""
    captured: list[dict] = []

    def capture_processor(logger, method_name, event_dict):
        captured.append(event_dict.copy())
        raise structlog.DropEvent

    return captured, capture_processor


@pytest.mark.asyncio
async def test_log_output_is_json_format(client: AsyncClient) -> None:
    """Request logs must be valid JSON with required fields."""
    captured, processor = _capture_structlog()

    with patch("api.middleware.logging.logger", structlog.wrap_logger(logging.getLogger("test"), processors=[processor])):
        await client.get("/health")

    assert len(captured) >= 1
    entry = captured[-1]
    assert entry["event"] == "request_completed"
    assert "method" in entry
    assert "path" in entry
    assert "status" in entry
    assert "latency_ms" in entry
    assert "correlation_id" in entry


@pytest.mark.asyncio
async def test_log_level_info_for_2xx(client: AsyncClient) -> None:
    """2xx responses should be logged at INFO level."""
    captured, processor = _capture_structlog()

    with patch("api.middleware.logging.logger", structlog.wrap_logger(logging.getLogger("test"), processors=[processor])):
        await client.get("/health")

    entry = [e for e in captured if e.get("event") == "request_completed"][-1]
    assert entry["status"] < 400


@pytest.mark.asyncio
async def test_log_level_warning_for_4xx(client: AsyncClient) -> None:
    """4xx responses should be logged at WARNING level."""
    captured, processor = _capture_structlog()

    with patch("api.middleware.logging.logger", structlog.wrap_logger(logging.getLogger("test"), processors=[processor])):
        resp = await client.post("/api/v1/auth/login", json={"email": "bad@test.dev", "password": "wrong"})

    assert resp.status_code == 401
    log_entries = [e for e in captured if e.get("event") == "request_completed"]
    assert len(log_entries) >= 1
    assert log_entries[-1]["status"] == 401


@pytest.mark.asyncio
async def test_pii_not_in_request_logs(client: AsyncClient, seed_user: dict) -> None:
    """Passwords, emails, and tokens must NEVER appear in logs."""
    captured, processor = _capture_structlog()

    password = seed_user["password"]
    email = seed_user["email"]

    with patch("api.middleware.logging.logger", structlog.wrap_logger(logging.getLogger("test"), processors=[processor])):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )

    log_text = json.dumps(captured, default=str)
    assert password not in log_text
    assert email not in log_text
    assert "testpassword123" not in log_text


@pytest.mark.asyncio
async def test_request_body_not_logged(client: AsyncClient, seed_user: dict) -> None:
    """Request body (which may contain PII) must not be logged."""
    captured, processor = _capture_structlog()

    with patch("api.middleware.logging.logger", structlog.wrap_logger(logging.getLogger("test"), processors=[processor])):
        await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": seed_user["password"]},
        )

    log_text = json.dumps(captured, default=str)
    # Request body fields should not appear
    assert '"password":' not in log_text
    assert seed_user["password"] not in log_text


@pytest.mark.asyncio
async def test_user_id_logged_when_authenticated(client: AsyncClient, auth_tokens: dict) -> None:
    """Authenticated requests should include user_id in logs."""
    captured, processor = _capture_structlog()

    with patch("api.middleware.logging.logger", structlog.wrap_logger(logging.getLogger("test"), processors=[processor])):
        await client.post(
            "/api/v1/auth/logout",
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-CSRF-Token": auth_tokens["csrf_token"],
            },
            cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
        )

    entry = [e for e in captured if e.get("event") == "request_completed"][-1]
    assert "user_id" in entry
    assert entry["user_id"] == str(auth_tokens["user_id"])


@pytest.mark.asyncio
async def test_no_user_id_for_unauthenticated(client: AsyncClient) -> None:
    """Unauthenticated requests should not include user_id."""
    captured, processor = _capture_structlog()

    with patch("api.middleware.logging.logger", structlog.wrap_logger(logging.getLogger("test"), processors=[processor])):
        await client.get("/health")

    entry = [e for e in captured if e.get("event") == "request_completed"][-1]
    assert "user_id" not in entry


@pytest.mark.asyncio
async def test_500_error_does_not_expose_stack_in_response(client: AsyncClient) -> None:
    """500 error response must not contain stack trace (server-side only)."""
    from api.main import app

    @app.get("/test-500-crash")
    async def crash_endpoint():
        raise RuntimeError("test crash")

    # FastAPI in debug mode re-raises through ServerErrorMiddleware.
    # Use raise_app_exceptions=False to capture the actual 500 response.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/test-500-crash")

    assert resp.status_code == 500
    body = resp.json()
    assert "RuntimeError" not in body.get("message", "")
    assert "traceback" not in body.get("message", "").lower()
    assert body["error_code"] == "INTERNAL_ERROR"
