"""Integration test conftest.

Overrides the parent conftest's `mock_rate_limiter_redis` autouse fixture so
that integration tests run against a real Redis instance.  This allows the
auth middleware revocation-blocklist check (and brute-force rate limiting) to
behave exactly as they do in production.

pytest-asyncio is configured with asyncio_default_fixture_loop_scope = "session"
(see pyproject.toml), so all async fixtures and test functions share a single
event loop for the duration of the test session.  Redis connection pools bind
to the loop they were first created on; because there is only one loop, pools
created by any fixture are valid for the entire session and do NOT need to be
reset between tests.

Requires: Redis running (start with `make test-integration` or `make up`).
"""

import pytest


@pytest.fixture(autouse=True)
def mock_rate_limiter_redis():
    """Integration tests use real Redis — no mocking.

    Overrides the same-named fixture in the parent conftest.py.
    All Redis calls (rate limiter, auth blocklist, logout setex) hit the
    actual Redis server on localhost:6379.
    """
    yield  # no patches applied
