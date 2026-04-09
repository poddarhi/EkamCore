"""Tests for S06-003: Diagnostics export endpoint.

Covers:
  - ZIP file structure (all expected files present)
  - PII stripping (emails, phone numbers, names removed)
  - Audit summary contains counts, not PII
  - Admin-only access
  - System info fields present
"""

from __future__ import annotations

import json
import zipfile
import io
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from api.services.diagnostics import strip_pii, strip_pii_from_dict


@pytest_asyncio.fixture
async def admin_tokens(client: AsyncClient, test_session_factory) -> dict:
    """Create an admin user and return auth tokens."""
    from api.db.models.user import User
    from api.db.models.workspace import Workspace
    from api.db.models.workspace_member import WorkspaceMember
    from api.services.auth import hash_password

    password = "adminpassword123"
    email = f"admin-diag-{uuid4().hex[:8]}@ekamcore.dev"

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
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
        await db.commit()

        user_id = user.id
        workspace_id = workspace.id

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    return {
        "access_token": data["access_token"],
        "user_id": user_id,
        "workspace_id": workspace_id,
    }


# ---------------------------------------------------------------------------
# PII Stripper unit tests
# ---------------------------------------------------------------------------


class TestStripPii:
    def test_strips_email(self):
        assert "[EMAIL]" in strip_pii("Contact john@example.com for details")

    def test_strips_multiple_emails(self):
        result = strip_pii("alice@a.com and bob@b.org")
        assert "alice" not in result
        assert "bob" not in result
        assert result.count("[EMAIL]") == 2

    def test_strips_phone_number(self):
        result = strip_pii("Call +1-555-123-4567")
        assert "555" not in result
        assert "[PHONE]" in result

    def test_strips_phone_without_country_code(self):
        result = strip_pii("Call 555-123-4567")
        assert "[PHONE]" in result

    def test_strips_names(self):
        result = strip_pii("Meeting with John Smith about the project")
        assert "John Smith" not in result
        assert "[NAME]" in result

    def test_preserves_non_pii_text(self):
        text = "System status: healthy, uptime: 3600s"
        assert strip_pii(text) == text

    def test_strips_from_dict(self):
        data = {
            "user": "john@example.com",
            "message": "Contact Alice Johnson",
            "count": 42,
            "nested": {"phone": "+1-555-000-1234"},
        }
        result = strip_pii_from_dict(data)
        assert "[EMAIL]" in result["user"]
        assert "[NAME]" in result["message"]
        assert result["count"] == 42
        assert "[PHONE]" in result["nested"]["phone"]

    def test_strips_from_list_in_dict(self):
        data = {
            "entries": ["bob@test.com", "normal text", {"name": "Jane Doe"}],
        }
        result = strip_pii_from_dict(data)
        assert "[EMAIL]" in result["entries"][0]
        assert result["entries"][1] == "normal text"
        assert "[NAME]" in result["entries"][2]["name"]


# ---------------------------------------------------------------------------
# Diagnostics ZIP structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagnostics_zip_structure(client: AsyncClient, admin_tokens: dict):
    """ZIP must contain all expected files."""
    response = await client.get(
        "/api/v1/admin/diagnostics",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers.get("content-disposition", "")

    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf, "r") as zf:
        names = set(zf.namelist())

    expected = {
        "system_info.json",
        "service_health.json",
        "container_stats.json",
        "audit_log_summary.json",
        "recent_errors.json",
    }
    assert names == expected


@pytest.mark.asyncio
async def test_diagnostics_system_info_fields(client: AsyncClient, admin_tokens: dict):
    response = await client.get(
        "/api/v1/admin/diagnostics",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200

    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf, "r") as zf:
        system_info = json.loads(zf.read("system_info.json"))

    assert "hostname" in system_info
    assert "os" in system_info
    assert "python_version" in system_info
    assert "environment" in system_info
    assert "current_phase" in system_info
    assert "collected_at" in system_info


@pytest.mark.asyncio
async def test_diagnostics_audit_summary_is_counts_only(
    client: AsyncClient, admin_tokens: dict
):
    response = await client.get(
        "/api/v1/admin/diagnostics",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf, "r") as zf:
        audit = json.loads(zf.read("audit_log_summary.json"))

    assert "events_by_action" in audit
    assert "total_events" in audit
    assert isinstance(audit["total_events"], int)
    for action, count in audit["events_by_action"].items():
        assert isinstance(count, int)
        assert "@" not in action


@pytest.mark.asyncio
async def test_diagnostics_no_pii_in_system_info(
    client: AsyncClient, admin_tokens: dict
):
    response = await client.get(
        "/api/v1/admin/diagnostics",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf, "r") as zf:
        for name in zf.namelist():
            content = zf.read(name).decode()
            assert "@ekamcore.dev" not in content, f"PII found in {name}"


@pytest.mark.asyncio
async def test_diagnostics_service_health_present(
    client: AsyncClient, admin_tokens: dict
):
    response = await client.get(
        "/api/v1/admin/diagnostics",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    buf = io.BytesIO(response.content)
    with zipfile.ZipFile(buf, "r") as zf:
        health = json.loads(zf.read("service_health.json"))

    assert "status" in health


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagnostics_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/diagnostics")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_diagnostics_requires_admin_role(client: AsyncClient, auth_tokens: dict):
    """Standard user should get 403."""
    response = await client.get(
        "/api/v1/admin/diagnostics",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403
