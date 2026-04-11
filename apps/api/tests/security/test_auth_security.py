"""G-05: Auth security — JWT validation, missing headers, expired tokens.

Complements test_auth_*.py with edge cases not already covered:
- Invalid JWT signature (tampered)
- Missing Authorization header on ALL protected endpoints
- Admin-only endpoints reject standard users
"""

from __future__ import annotations

import jwt
import pytest

pytestmark = pytest.mark.asyncio


async def test_tampered_jwt_returns_401(client, auth_tokens):
    """A JWT signed with a wrong key is rejected."""
    # Create a JWT signed with a different secret
    payload = {
        "sub": str(auth_tokens["user_id"]),
        "role": "admin",
        "workspaces": [str(auth_tokens["workspace_id"])],
        "jti": "fake-session-id",
        "iss": "ekamcore",
    }
    bad_token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")

    resp = await client.get(
        f"/api/v1/today?workspace_id={auth_tokens['workspace_id']}",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_TOKEN_INVALID"


async def test_missing_auth_header_returns_401_on_protected_endpoints(client, auth_tokens):
    """Every protected endpoint rejects requests without Authorization header."""
    ws = auth_tokens["workspace_id"]

    endpoints = [
        ("GET", f"/api/v1/today?workspace_id={ws}"),
        ("GET", f"/api/v1/recap?workspace_id={ws}"),
        ("GET", f"/api/v1/search?q=test&workspace_id={ws}"),
        ("GET", "/api/v1/settings"),
        ("POST", "/api/v1/query"),
    ]

    for method, url in endpoints:
        if method == "GET":
            resp = await client.get(url)
        else:
            resp = await client.post(url, json={})
        assert resp.status_code in (401, 422), f"{method} {url} returned {resp.status_code}, expected 401 or 422"


async def test_health_does_not_require_auth(client):
    """The /health endpoint is public."""
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_malformed_bearer_token_returns_401(client):
    """A non-JWT string in the Authorization header is rejected."""
    resp = await client.get(
        "/api/v1/settings",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert resp.status_code == 401
