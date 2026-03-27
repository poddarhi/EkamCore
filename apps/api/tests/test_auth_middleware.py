"""Tests for the get_current_user authentication middleware."""

import pytest
from httpx import AsyncClient

CSRF_TOKEN = "test-csrf-token-for-middleware-tests"


@pytest.mark.asyncio
async def test_valid_token(client: AsyncClient, auth_tokens: dict) -> None:
    """Authenticated request to a protected endpoint succeeds."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": auth_tokens["csrf_token"],
        },
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    # 204 means the middleware accepted the token and the handler ran
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_missing_token(client: AsyncClient) -> None:
    """Request without Authorization header is rejected."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": CSRF_TOKEN},
        cookies={"ekamcore_csrf": CSRF_TOKEN},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "AUTH_TOKEN_MISSING"


@pytest.mark.asyncio
async def test_malformed_token(client: AsyncClient) -> None:
    """Request with a garbage Bearer token is rejected."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": "Bearer not.a.valid.jwt",
            "X-CSRF-Token": CSRF_TOKEN,
        },
        cookies={"ekamcore_csrf": CSRF_TOKEN},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "AUTH_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_expired_token(client: AsyncClient, seed_user: dict) -> None:
    """Request with an expired JWT is rejected with AUTH_TOKEN_EXPIRED."""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from jose import jwt

    from api.config import settings

    # Manually craft an expired token
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(seed_user["user_id"]),
        "role": "standard",
        "workspaces": [str(seed_user["workspace_id"])],
        "jti": str(uuid4()),
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
        "iss": "ekamcore",
    }
    expired_token = jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {expired_token}",
            "X-CSRF-Token": CSRF_TOKEN,
        },
        cookies={"ekamcore_csrf": CSRF_TOKEN},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "AUTH_TOKEN_EXPIRED"
