"""Integration tests for GET /api/v1/admin/packs (S14-002)."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.auth import hash_password


@pytest_asyncio.fixture
async def admin_seed(test_session_factory):
    email = f"pack-admin-{uuid4().hex[:8]}@ekamcore.dev"
    password = "adminpassword123"
    async with test_session_factory() as db:
        user = User(
            email=email,
            display_name="Pack Admin",
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        workspace = Workspace(
            name="Pack Admin Workspace", type="personal", owner_id=user.id
        )
        db.add(workspace)
        await db.flush()
        db.add(
            WorkspaceMember(
                workspace_id=workspace.id, user_id=user.id, role="admin"
            )
        )
        await db.commit()
        return {"email": email, "password": password}


@pytest_asyncio.fixture
async def admin_tokens(client, admin_seed):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_seed["email"], "password": admin_seed["password"]},
    )
    assert response.status_code == 200
    return {"access_token": response.json()["access_token"]}


@pytest.mark.asyncio
async def test_list_packs_returns_pla_metadata(client, admin_tokens):
    response = await client.get(
        "/api/v1/admin/packs",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "packs" in body
    assert "load_errors" in body

    pla = next(
        (p for p in body["packs"] if p["pack_id"] == "pla"), None
    )
    assert pla is not None, "PLA pack should be loaded from packs/pla/manifest.yaml"

    assert pla["name"] == "Personal Life Assistant"
    assert pla["version"] == "1.0.0"
    assert "invoke:llm" in pla["capabilities"]
    assert "read:trusted_persons" in pla["capabilities"]
    assert "follow_up_suggestion" in pla["card_types"]
    assert pla["resource_limits"]["max_execution_time_seconds"] == 300
    assert pla["schedule"]["daily"] == "06:00"
    assert pla["schedule"]["weekly"] == "monday 08:00"


@pytest.mark.asyncio
async def test_list_packs_reports_disabled_when_flag_off(
    client, admin_tokens
):
    # Flags default off in test env, so enabled must be False.
    response = await client.get(
        "/api/v1/admin/packs",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    body = response.json()
    pla = next(p for p in body["packs"] if p["pack_id"] == "pla")
    assert pla["enabled"] is False


@pytest.mark.asyncio
async def test_list_packs_requires_admin(client, auth_tokens):
    response = await client.get(
        "/api/v1/admin/packs",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ADMIN_REQUIRED"


@pytest.mark.asyncio
async def test_list_packs_unauth_is_401(client):
    response = await client.get("/api/v1/admin/packs")
    assert response.status_code == 401
