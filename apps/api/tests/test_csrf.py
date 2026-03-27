"""Tests for CSRF double-submit cookie protection (S02-007)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_without_csrf_token_rejected(client: AsyncClient, auth_tokens: dict) -> None:
    """POST to a CSRF-protected endpoint without CSRF token returns 403."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error_code"] == "CSRF_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_post_with_wrong_csrf_token_rejected(client: AsyncClient, auth_tokens: dict) -> None:
    """POST with mismatched CSRF cookie and header returns 403."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": "wrong-csrf-token",
        },
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error_code"] == "CSRF_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_post_with_correct_csrf_token_passes(client: AsyncClient, auth_tokens: dict) -> None:
    """POST with matching CSRF cookie and header succeeds."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": auth_tokens["csrf_token"],
        },
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_login_does_not_require_csrf(client: AsyncClient, seed_user: dict) -> None:
    """POST /login is exempt from CSRF — no session exists yet."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_sets_csrf_cookie(client: AsyncClient, seed_user: dict) -> None:
    """Login response includes an ekamcore_csrf cookie."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert response.status_code == 200
    assert "ekamcore_csrf" in response.cookies
    csrf_value = response.cookies["ekamcore_csrf"]
    assert len(csrf_value) == 64  # 32 bytes hex = 64 chars


@pytest.mark.asyncio
async def test_refresh_rotates_csrf_cookie(client: AsyncClient, seed_user: dict) -> None:
    """Refresh response includes a new ekamcore_csrf cookie."""
    # Login first
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert login_resp.status_code == 200
    old_csrf = login_resp.cookies.get("ekamcore_csrf")
    refresh_cookie = login_resp.cookies.get("ekamcore_refresh")
    assert old_csrf
    assert refresh_cookie

    # Refresh
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": refresh_cookie},
    )
    assert refresh_resp.status_code == 200
    new_csrf = refresh_resp.cookies.get("ekamcore_csrf")
    assert new_csrf
    assert new_csrf != old_csrf


@pytest.mark.asyncio
async def test_csrf_header_only_no_cookie_rejected(client: AsyncClient, auth_tokens: dict) -> None:
    """CSRF header present but no cookie returns 403."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": "some-token",
        },
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "CSRF_VALIDATION_FAILED"
