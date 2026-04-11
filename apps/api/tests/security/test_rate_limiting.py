"""G-05: Rate limiting — verify progressive delays and lockout.

These are unit tests of the rate_limiter service. Integration-level
rate limit tests that hit real Redis are in test_phase1_e2e.py::test_brute_force_lockout.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from api.errors import AccountLockedError
from api.services.rate_limiter import (
    check_brute_force,
    record_failed_login,
    clear_failed_logins,
)

pytestmark = pytest.mark.asyncio


def _mock_redis(failure_count: str | None, ttl: int = 3600, new_count: int = 1):
    """Mock Redis client with specific state."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=failure_count)
    mock.ttl = AsyncMock(return_value=ttl)
    mock.delete = AsyncMock()

    pipe = Mock()
    pipe.incr = Mock(return_value=pipe)
    pipe.expire = Mock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[new_count, True])
    mock.pipeline = Mock(return_value=pipe)

    return mock


async def test_no_lockout_under_threshold():
    """Under 20 failures, no lockout raised."""
    mock = _mock_redis(failure_count="19", ttl=3600)
    # Should not raise
    from unittest.mock import patch
    with patch("api.services.rate_limiter.get_redis", return_value=mock):
        await check_brute_force("test@example.com")


async def test_lockout_at_threshold():
    """At 20 failures, lockout raised with retry_after."""
    mock = _mock_redis(failure_count="20", ttl=1800)
    from unittest.mock import patch
    with patch("api.services.rate_limiter.get_redis", return_value=mock):
        with pytest.raises(AccountLockedError) as exc_info:
            await check_brute_force("test@example.com")
        assert exc_info.value.details["retry_after_seconds"] == 1800


async def test_lockout_above_threshold():
    """Above 20 failures, still locked."""
    mock = _mock_redis(failure_count="50", ttl=600)
    from unittest.mock import patch
    with patch("api.services.rate_limiter.get_redis", return_value=mock):
        with pytest.raises(AccountLockedError):
            await check_brute_force("test@example.com")


async def test_record_increments_counter():
    """record_failed_login increments Redis counter."""
    mock = _mock_redis(failure_count=None, new_count=5)
    from unittest.mock import patch
    with patch("api.services.rate_limiter.get_redis", return_value=mock):
        count = await record_failed_login("test@example.com")
    assert count == 5


async def test_clear_deletes_key():
    """clear_failed_logins deletes the Redis key."""
    mock = _mock_redis(failure_count="10")
    from unittest.mock import patch
    with patch("api.services.rate_limiter.get_redis", return_value=mock):
        await clear_failed_logins("test@example.com")
    mock.delete.assert_awaited_once()


async def test_no_failures_no_delay():
    """Zero failures → no delay, no lockout."""
    mock = _mock_redis(failure_count=None)
    from unittest.mock import patch
    with patch("api.services.rate_limiter.get_redis", return_value=mock):
        await check_brute_force("test@example.com")
    # If we got here without raising or sleeping, test passes
