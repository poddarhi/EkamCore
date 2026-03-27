"""Tests for POST /api/v1/auth/login."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, seed_user: dict) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 15 * 60
    # Refresh token is set as HttpOnly cookie
    assert "ekamcore_refresh" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, seed_user: dict) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": "wrongpassword"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_wrong_email(client: AsyncClient, seed_user: dict) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@ekamcore.dev", "password": "testpassword123"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_missing_fields(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
