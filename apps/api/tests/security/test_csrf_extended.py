"""G-05: Extended CSRF tests beyond what test_csrf.py covers.

Focuses on write endpoints across different routers to confirm
CSRF is consistently enforced on all state-changing methods.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_patch_settings_without_csrf_returns_403(client, auth_tokens):
    """PATCH without CSRF token → 403."""
    resp = await client.patch(
        "/api/v1/settings",
        json={"settings": {"date_format": "YYYY-MM-DD"}},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "CSRF_VALIDATION_FAILED"


async def test_delete_settings_without_csrf_returns_403(client, auth_tokens):
    """DELETE without CSRF token → 403."""
    resp = await client.delete(
        "/api/v1/settings/date_format",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 403


async def test_post_sources_without_csrf_returns_403(client, auth_tokens):
    """POST /sources without CSRF → 403."""
    resp = await client.post(
        "/api/v1/sources",
        json={"name": "Test", "type": "local_folder"},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 403


async def test_get_settings_without_csrf_succeeds(client, auth_tokens):
    """GET does NOT require CSRF (safe method)."""
    resp = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 200


async def test_mismatched_csrf_returns_403(client, auth_tokens):
    """Cookie and header values don't match → 403."""
    resp = await client.patch(
        "/api/v1/settings",
        json={"settings": {"date_format": "YYYY-MM-DD"}},
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": "header_value_abc",
        },
        cookies={"ekamcore_csrf": "different_cookie_value"},
    )
    assert resp.status_code == 403
