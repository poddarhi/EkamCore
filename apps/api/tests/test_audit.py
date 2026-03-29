"""Tests for audit logging: event creation and PII protection."""

import asyncio
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.audit_log import AuditLog
from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.auth import hash_password


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _all_audit_events(db: AsyncSession, action: str | None = None) -> list[AuditLog]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return list((await db.execute(stmt)).scalars().all())


async def _make_admin_user(test_session_factory) -> dict:
    """Create an admin user with workspace; return credentials dict."""
    email = f"admin-{uuid4().hex[:8]}@ekamcore.dev"
    password = "adminpass123"
    async with test_session_factory() as db:
        user = User(
            email=email,
            display_name="Admin User",
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        workspace = Workspace(name="Admin WS", type="personal", owner_id=user.id)
        db.add(workspace)
        await db.flush()

        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin")
        db.add(member)
        await db.commit()

        return {"user_id": user.id, "email": email, "password": password, "workspace_id": workspace.id}


# ---------------------------------------------------------------------------
# Auth event tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_success_creates_audit_event(
    client: AsyncClient, seed_user: dict, test_session_factory
) -> None:
    """Successful login creates a login_success audit entry with no PII."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert response.status_code == 200

    # Allow any background tasks to complete
    await asyncio.sleep(0)

    async with test_session_factory() as db:
        entries = await _all_audit_events(db, action="login_success")

    assert len(entries) >= 1
    entry = entries[-1]
    assert entry.user_id == seed_user["user_id"]
    assert entry.object_type == "session"
    assert entry.old_state is None
    assert entry.new_state is None


@pytest.mark.asyncio
async def test_login_failure_creates_audit_event(
    client: AsyncClient, seed_user: dict, test_session_factory
) -> None:
    """Failed login (wrong password) creates a login_failure audit entry."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401

    await asyncio.sleep(0)

    async with test_session_factory() as db:
        entries = await _all_audit_events(db, action="login_failure")

    assert len(entries) >= 1
    entry = entries[-1]
    assert entry.object_type == "session"
    assert entry.old_state is None
    assert entry.new_state is None


@pytest.mark.asyncio
async def test_login_failure_unknown_email_returns_401(client: AsyncClient) -> None:
    """Login with an unknown email returns 401 (does not leak user existence)."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "anything"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_logout_creates_audit_event(
    client: AsyncClient, auth_tokens: dict, test_session_factory
) -> None:
    """Logout creates a logout audit entry."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": auth_tokens["csrf_token"],
        },
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 204

    await asyncio.sleep(0)

    async with test_session_factory() as db:
        entries = await _all_audit_events(db, action="logout")

    assert len(entries) >= 1
    entry = entries[-1]
    assert entry.user_id == auth_tokens["user_id"]
    assert entry.object_type == "session"


@pytest.mark.asyncio
async def test_token_refresh_creates_audit_event(
    client: AsyncClient, auth_tokens: dict, test_session_factory
) -> None:
    """Token refresh creates a token_refresh audit entry."""
    response = await client.post(
        "/api/v1/auth/refresh",
        cookies={"ekamcore_refresh": auth_tokens["refresh_cookie"]},
    )
    assert response.status_code == 200

    await asyncio.sleep(0)

    async with test_session_factory() as db:
        entries = await _all_audit_events(db, action="token_refresh")

    assert len(entries) >= 1
    entry = entries[-1]
    assert entry.user_id == auth_tokens["user_id"]


# ---------------------------------------------------------------------------
# Source event tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_source_created_creates_audit_event(
    client: AsyncClient, auth_tokens: dict, test_session_factory
) -> None:
    """Creating a source creates a source_created audit entry."""
    response = await client.post(
        "/api/v1/sources",
        json={"name": "Audit Test Contacts", "type": "contacts"},
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": auth_tokens["csrf_token"],
        },
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 201

    await asyncio.sleep(0)

    async with test_session_factory() as db:
        entries = await _all_audit_events(db, action="source_created")

    assert len(entries) >= 1
    entry = entries[-1]
    assert entry.object_type == "source"
    assert entry.user_id == auth_tokens["user_id"]
    assert entry.new_state is not None
    assert entry.new_state.get("type") == "contacts"
    assert entry.new_state.get("name") == "Audit Test Contacts"
    assert "password" not in str(entry.new_state)
    assert "token" not in str(entry.new_state)


@pytest.mark.asyncio
async def test_source_deleted_creates_audit_event(
    client: AsyncClient, auth_tokens: dict, test_session_factory
) -> None:
    """Deleting a source creates a source_deleted audit entry with old_state."""
    # Create the source first
    create_resp = await client.post(
        "/api/v1/sources",
        json={"name": "To Delete", "type": "contacts"},
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": auth_tokens["csrf_token"],
        },
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert create_resp.status_code == 201
    source_id = create_resp.json()["id"]

    # Now delete it
    delete_resp = await client.delete(
        f"/api/v1/sources/{source_id}",
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": auth_tokens["csrf_token"],
        },
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert delete_resp.status_code == 204

    await asyncio.sleep(0)

    async with test_session_factory() as db:
        entries = await _all_audit_events(db, action="source_deleted")

    assert len(entries) >= 1
    entry = entries[-1]
    assert entry.object_type == "source"
    assert entry.user_id == auth_tokens["user_id"]
    assert entry.old_state is not None
    assert entry.old_state.get("name") == "To Delete"
    assert entry.new_state is None


# ---------------------------------------------------------------------------
# PII protection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_entries_contain_no_pii(
    client: AsyncClient, seed_user: dict, test_session_factory
) -> None:
    """All audit entries must never contain passwords, tokens, or emails."""
    # Generate several audit events
    await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": "wrong"},
    )
    await asyncio.sleep(0)

    async with test_session_factory() as db:
        entries = await _all_audit_events(db)

    banned_keywords = {"password", "passwd", "secret", "bearer", "token", "credential"}
    for entry in entries:
        for state in (entry.old_state, entry.new_state, entry.metadata_json):
            if state:
                state_str = str(state).lower()
                for kw in banned_keywords:
                    assert kw not in state_str, (
                        f"PII keyword '{kw}' found in audit entry {entry.id} ({entry.action})"
                    )


# ---------------------------------------------------------------------------
# Admin endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_endpoint_requires_admin(
    client: AsyncClient, auth_tokens: dict
) -> None:
    """Standard-role user gets 403 from the audit-log endpoint."""
    response = await client.get(
        "/api/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ADMIN_REQUIRED"


@pytest.mark.asyncio
async def test_audit_log_endpoint_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated request gets 401."""
    response = await client.get("/api/v1/admin/audit-log")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_audit_log_endpoint_admin_access(
    client: AsyncClient, test_session_factory
) -> None:
    """Admin user can query the audit log and receives paginated results."""
    admin = await _make_admin_user(test_session_factory)

    # Login as admin to get a token
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": admin["email"], "password": admin["password"]},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    response = await client.get(
        "/api/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "total_in_page" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_audit_log_endpoint_action_filter(
    client: AsyncClient, test_session_factory
) -> None:
    """action= query param filters results to only that action type."""
    admin = await _make_admin_user(test_session_factory)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": admin["email"], "password": admin["password"]},
    )
    token = login_resp.json()["access_token"]

    response = await client.get(
        "/api/v1/admin/audit-log",
        params={"action": "login_success"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["action"] == "login_success"


@pytest.mark.asyncio
async def test_audit_log_endpoint_cursor_pagination(
    client: AsyncClient, test_session_factory
) -> None:
    """Cursor-based pagination advances through results without repeating entries."""
    admin = await _make_admin_user(test_session_factory)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": admin["email"], "password": admin["password"]},
    )
    token = login_resp.json()["access_token"]

    # Fetch first page (small per_page to force pagination)
    page1 = await client.get(
        "/api/v1/admin/audit-log",
        params={"per_page": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page1.status_code == 200
    d1 = page1.json()

    if d1["next_cursor"] is not None:
        # Fetch second page using cursor
        page2 = await client.get(
            "/api/v1/admin/audit-log",
            params={"per_page": 2, "cursor": d1["next_cursor"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert page2.status_code == 200
        d2 = page2.json()

        # IDs must not overlap between pages
        ids1 = {item["id"] for item in d1["items"]}
        ids2 = {item["id"] for item in d2["items"]}
        assert ids1.isdisjoint(ids2), "Pagination returned duplicate entries"
