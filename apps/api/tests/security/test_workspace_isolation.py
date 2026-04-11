"""G-05: Workspace isolation — verify user A cannot access user B's data.

Tests every data endpoint to confirm workspace_id enforcement.
Complements test_phase1_e2e.py::test_workspace_isolation which covers
the GET paths; this file adds write-path isolation tests.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.auth import hash_password

pytestmark = pytest.mark.asyncio


async def _create_user_and_workspace(test_session_factory, *, role: str = "standard") -> dict:
    email = f"sec-{uuid4().hex[:8]}@ekamcore.dev"
    password = "testpassword123"
    async with test_session_factory() as db:
        user = User(email=email, display_name="Sec User", password_hash=hash_password(password), role=role, is_active=True)
        db.add(user)
        await db.flush()
        ws = Workspace(name=f"WS-{uuid4().hex[:6]}", type="personal", owner_id=user.id)
        db.add(ws)
        await db.flush()
        member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin")
        db.add(member)
        await db.commit()
        return {"email": email, "password": password, "user_id": user.id, "workspace_id": ws.id}


async def _login(client: AsyncClient, creds: dict) -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]})
    assert resp.status_code == 200
    data = resp.json()
    return {"access_token": data["access_token"], "csrf_token": resp.cookies.get("ekamcore_csrf"), **creds}


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── Read isolation ──


async def test_today_workspace_isolation(client, test_session_factory):
    a = await _login(client, await _create_user_and_workspace(test_session_factory))
    b = await _login(client, await _create_user_and_workspace(test_session_factory))

    # User B queries user A's workspace → 403
    resp = await client.get(f"/api/v1/today?workspace_id={a['workspace_id']}", headers=_auth(b))
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "WORKSPACE_ACCESS_DENIED"


async def test_search_workspace_isolation(client, test_session_factory):
    a = await _login(client, await _create_user_and_workspace(test_session_factory))
    b = await _login(client, await _create_user_and_workspace(test_session_factory))

    resp = await client.get(f"/api/v1/search?q=test&workspace_id={a['workspace_id']}", headers=_auth(b))
    assert resp.status_code == 403


async def test_query_workspace_isolation(client, test_session_factory):
    a = await _login(client, await _create_user_and_workspace(test_session_factory))
    b = await _login(client, await _create_user_and_workspace(test_session_factory))

    resp = await client.post("/api/v1/query", json={"query": "hello", "workspace_id": str(a["workspace_id"])}, headers=_auth(b))
    assert resp.status_code == 403


async def test_recap_workspace_isolation(client, test_session_factory):
    a = await _login(client, await _create_user_and_workspace(test_session_factory))
    b = await _login(client, await _create_user_and_workspace(test_session_factory))

    resp = await client.get(f"/api/v1/recap?workspace_id={a['workspace_id']}", headers=_auth(b))
    assert resp.status_code == 403


async def test_settings_workspace_isolation(client, test_session_factory):
    """User A's settings are not accessible by user B (implicitly, since
    settings use the JWT's workspace_id, not a query parameter)."""
    a = await _login(client, await _create_user_and_workspace(test_session_factory))
    b = await _login(client, await _create_user_and_workspace(test_session_factory))

    # User A sets a value
    csrf_a = a.get("csrf_token", "")
    await client.patch(
        "/api/v1/settings",
        json={"settings": {"date_format": "YYYY-MM-DD"}},
        headers={"Authorization": f"Bearer {a['access_token']}", "X-CSRF-Token": csrf_a},
        cookies={"ekamcore_csrf": csrf_a},
    )

    # User B reads their own settings — should see the default, not A's value
    resp = await client.get("/api/v1/settings", headers=_auth(b))
    assert resp.status_code == 200
    assert resp.json()["settings"]["date_format"] == "MM/DD/YYYY"


# ── Write isolation ──


async def test_source_create_ignores_body_workspace_id(client, test_session_factory):
    """Even if user B passes workspace_id=A in the body, the router uses
    the JWT's workspace — B's source lands in B's workspace, not A's."""
    a = await _login(client, await _create_user_and_workspace(test_session_factory))
    b = await _login(client, await _create_user_and_workspace(test_session_factory))

    csrf_b = b.get("csrf_token", "")
    resp = await client.post(
        "/api/v1/sources",
        json={"name": "Attempted Injection", "type": "local_folder", "path": "/tmp", "workspace_id": str(a["workspace_id"])},
        headers={"Authorization": f"Bearer {b['access_token']}", "X-CSRF-Token": csrf_b},
        cookies={"ekamcore_csrf": csrf_b},
    )
    # Source is created, but in B's workspace (not A's)
    assert resp.status_code == 201
    source = resp.json()
    # The workspace_id in the response should be B's, not A's
    assert source["workspace_id"] == str(b["workspace_id"])
    assert source["workspace_id"] != str(a["workspace_id"])


async def test_admin_jobs_requires_admin_role(client, test_session_factory):
    """Standard user cannot access admin endpoints."""
    user = await _login(client, await _create_user_and_workspace(test_session_factory))
    resp = await client.get("/api/v1/admin/jobs", headers=_auth(user))
    assert resp.status_code == 403

    resp = await client.get("/api/v1/admin/storage", headers=_auth(user))
    assert resp.status_code == 403
