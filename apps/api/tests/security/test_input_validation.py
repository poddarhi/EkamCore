"""G-05: Input validation — SQL injection, XSS, oversized payloads.

Verifies that the API safely handles malicious or oversized inputs.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_sql_injection_in_search_query(client, auth_tokens):
    """SQL injection attempts in search query are parameterized, no effect."""
    ws = auth_tokens["workspace_id"]

    injections = [
        "'; DROP TABLE users;--",
        "\" OR 1=1 --",
        "1; SELECT * FROM pg_shadow",
        "' UNION SELECT password FROM users--",
    ]

    for payload in injections:
        resp = await client.get(
            f"/api/v1/search?q={payload}&workspace_id={ws}",
            headers=_auth(auth_tokens),
        )
        # Should return 200 with empty results (parameterized query), not 500
        assert resp.status_code == 200, f"SQL injection test failed for: {payload}"
        data = resp.json()
        assert "data" in data  # Normal response shape, no error


async def test_xss_in_search_query_not_reflected(client, auth_tokens):
    """XSS payload in search query is not reflected raw in response."""
    ws = auth_tokens["workspace_id"]
    xss = "<script>alert('xss')</script>"

    resp = await client.get(
        f"/api/v1/search?q={xss}&workspace_id={ws}",
        headers=_auth(auth_tokens),
    )
    assert resp.status_code == 200
    body = resp.text
    # The literal <script> tag should never appear in the response
    assert "<script>" not in body


async def test_query_exceeding_max_length_returns_422(client, auth_tokens):
    """Query field max_length=500 — exceeding returns validation error."""
    ws = auth_tokens["workspace_id"]
    long_query = "a" * 501

    resp = await client.post(
        "/api/v1/query",
        json={"query": long_query, "workspace_id": str(ws)},
        headers=_auth(auth_tokens),
    )
    assert resp.status_code == 422


async def test_search_query_exceeding_max_length(client, auth_tokens):
    """GET /search q parameter max_length=200."""
    ws = auth_tokens["workspace_id"]
    long_query = "a" * 201

    resp = await client.get(
        f"/api/v1/search?q={long_query}&workspace_id={ws}",
        headers=_auth(auth_tokens),
    )
    assert resp.status_code == 422


async def test_extra_fields_in_post_body_ignored(client, auth_tokens):
    """Pydantic models strip unknown fields — mass assignment blocked."""
    ws = auth_tokens["workspace_id"]
    csrf = auth_tokens.get("csrf_token", "")

    resp = await client.patch(
        "/api/v1/settings",
        json={
            "settings": {"date_format": "YYYY-MM-DD"},
            "is_admin": True,  # extra field — should be ignored
            "role": "superuser",  # extra field
        },
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": csrf,
        },
        cookies={"ekamcore_csrf": csrf},
    )
    # Should succeed (extra fields stripped by Pydantic), not crash
    assert resp.status_code == 200


async def test_empty_query_returns_422(client, auth_tokens):
    """Empty string in min_length=1 field returns 422."""
    ws = auth_tokens["workspace_id"]

    resp = await client.post(
        "/api/v1/query",
        json={"query": "", "workspace_id": str(ws)},
        headers=_auth(auth_tokens),
    )
    assert resp.status_code == 422
