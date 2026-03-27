"""Tests for brute-force protection (S02-002)."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import AsyncClient


def _make_mock_redis(failure_count: str | None, new_count: int = 0, ttl: int = 3600) -> Mock:
    """Build a mock Redis client with the expected call signatures."""
    pipe = Mock()
    pipe.incr = Mock(return_value=pipe)
    pipe.expire = Mock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[new_count, True])

    mock = AsyncMock()
    mock.get = AsyncMock(return_value=failure_count)
    mock.ttl = AsyncMock(return_value=ttl)
    mock.delete = AsyncMock()
    # pipeline() is synchronous in redis-py, returns a Pipeline object
    mock.pipeline = Mock(return_value=pipe)
    return mock


@pytest.mark.asyncio
async def test_no_delay_under_threshold(client: AsyncClient, seed_user: dict) -> None:
    """Fewer than 3 failures should not trigger any delay."""
    mock_redis = _make_mock_redis("2", new_count=3)

    with patch("api.services.rate_limiter.get_redis", return_value=mock_redis):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": "wrongpassword"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_progressive_delay_at_3_failures(client: AsyncClient, seed_user: dict) -> None:
    """At 3 failures, a 1-second delay should be applied."""
    mock_redis = _make_mock_redis("3", new_count=4)

    with (
        patch("api.services.rate_limiter.get_redis", return_value=mock_redis),
        patch("api.services.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": "wrongpassword"},
        )
    assert response.status_code == 401
    mock_sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_progressive_delay_at_5_failures(client: AsyncClient, seed_user: dict) -> None:
    """At 5 failures, a 5-second delay should be applied."""
    mock_redis = _make_mock_redis("5", new_count=6)

    with (
        patch("api.services.rate_limiter.get_redis", return_value=mock_redis),
        patch("api.services.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": "wrongpassword"},
        )
    assert response.status_code == 401
    mock_sleep.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_progressive_delay_at_10_failures(client: AsyncClient, seed_user: dict) -> None:
    """At 10 failures, a 30-second delay should be applied."""
    mock_redis = _make_mock_redis("10", new_count=11)

    with (
        patch("api.services.rate_limiter.get_redis", return_value=mock_redis),
        patch("api.services.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": "wrongpassword"},
        )
    assert response.status_code == 401
    mock_sleep.assert_awaited_once_with(30)


@pytest.mark.asyncio
async def test_lockout_at_20_failures(client: AsyncClient, seed_user: dict) -> None:
    """At 20 failures, the account should be locked (423)."""
    mock_redis = _make_mock_redis("20", ttl=2400)

    with patch("api.services.rate_limiter.get_redis", return_value=mock_redis):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": "wrongpassword"},
        )
    assert response.status_code == 423
    data = response.json()
    assert data["error_code"] == "AUTH_ACCOUNT_LOCKED"
    assert data["details"]["retry_after_seconds"] == 2400


@pytest.mark.asyncio
async def test_lockout_includes_retry_after(client: AsyncClient, seed_user: dict) -> None:
    """Lockout response should include remaining TTL as retry_after_seconds."""
    mock_redis = _make_mock_redis("25", ttl=1800)

    with patch("api.services.rate_limiter.get_redis", return_value=mock_redis):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": "wrongpassword"},
        )
    assert response.status_code == 423
    assert response.json()["details"]["retry_after_seconds"] == 1800


@pytest.mark.asyncio
async def test_successful_login_clears_counter(client: AsyncClient, seed_user: dict) -> None:
    """A successful login should DELETE the failure counter."""
    mock_redis = _make_mock_redis("2")

    with patch("api.services.rate_limiter.get_redis", return_value=mock_redis):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": seed_user["password"]},
        )
    assert response.status_code == 200
    mock_redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_failures_no_delay(client: AsyncClient, seed_user: dict) -> None:
    """Zero failures (key doesn't exist) should cause no delay and succeed."""
    mock_redis = _make_mock_redis(None)

    with patch("api.services.rate_limiter.get_redis", return_value=mock_redis):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seed_user["email"], "password": seed_user["password"]},
        )
    assert response.status_code == 200
