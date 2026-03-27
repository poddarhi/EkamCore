"""Tests for POST /api/v1/auth/logout."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient, auth_tokens: dict) -> None:
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_logout_already_logged_out(client: AsyncClient, auth_tokens: dict) -> None:
    # First logout
    resp1 = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp1.status_code == 204

    # Second logout with same token — still succeeds (idempotent, session already revoked)
    resp2 = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp2.status_code == 204
