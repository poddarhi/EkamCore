"""Tests for POST /api/v1/auth/refresh."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient, seed_user: dict) -> None:
    # Login first
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert login_resp.status_code == 200
    refresh_cookie = login_resp.cookies.get("ekamcore_refresh")
    assert refresh_cookie

    # Refresh using the cookie
    response = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": refresh_cookie},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # New refresh token cookie should be set
    assert "ekamcore_refresh" in response.cookies


@pytest.mark.asyncio
async def test_refresh_missing_cookie(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "AUTH_REFRESH_MISSING"


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": "totally-invalid-token"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "AUTH_REFRESH_INVALID"


@pytest.mark.asyncio
async def test_refresh_replay_detection(client: AsyncClient, seed_user: dict) -> None:
    """Using an already-rotated refresh token should revoke all user sessions."""
    # Login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    old_refresh = login_resp.cookies.get("ekamcore_refresh")
    assert old_refresh

    # First refresh — succeeds, rotates the token
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": old_refresh},
    )
    assert refresh_resp.status_code == 200
    new_refresh = refresh_resp.cookies.get("ekamcore_refresh")
    assert new_refresh

    # Replay the OLD token — should detect replay and revoke
    replay_resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": old_refresh},
    )
    assert replay_resp.status_code == 401
    data = replay_resp.json()
    assert data["error_code"] == "AUTH_REFRESH_REVOKED"

    # Even the new token should now be revoked (all sessions killed)
    revoked_resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": new_refresh},
    )
    assert revoked_resp.status_code == 401
