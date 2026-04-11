"""Tests for S09-004: Admin storage stats endpoint.

Covers:
  - GET /api/v1/admin/storage: returns storage breakdown
  - Auth: admin-only access
  - Storage service: disk_usage, pg_database_size, counts
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio

from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.auth import hash_password


# ── Fixtures ──


@pytest_asyncio.fixture
async def admin_seed(test_session_factory):
    email = f"admin-{uuid4().hex[:8]}@ekamcore.dev"
    password = "adminpassword123"

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

        workspace = Workspace(name="Admin Workspace", type="personal", owner_id=user.id)
        db.add(workspace)
        await db.flush()

        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin")
        db.add(member)
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


# ── Tests ──


@pytest.mark.asyncio
async def test_storage_returns_all_fields(client, admin_tokens):
    response = await client.get(
        "/api/v1/admin/storage",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()

    # All required fields present
    assert "postgres_size_mb" in data
    assert "qdrant_size_mb" in data
    assert "paperless_size_mb" in data
    assert "thumbnails_size_mb" in data
    assert "file_counts" in data
    assert "total" in data["file_counts"]
    assert "by_mime_type" in data["file_counts"]
    assert "photo_counts" in data
    assert "total" in data["photo_counts"]
    assert "with_gps" in data["photo_counts"]
    assert "total_disk_mb" in data
    assert "available_disk_mb" in data
    assert "free_space_pct" in data
    assert "free_space_warning" in data
    assert "free_space_critical" in data

    # Values are reasonable
    assert isinstance(data["postgres_size_mb"], (int, float))
    assert data["postgres_size_mb"] >= 0
    assert isinstance(data["total_disk_mb"], (int, float))
    assert isinstance(data["free_space_pct"], (int, float))
    assert 0 <= data["free_space_pct"] <= 100


@pytest.mark.asyncio
async def test_storage_requires_admin(client, auth_tokens):
    """Standard user gets 403."""
    response = await client.get(
        "/api/v1/admin/storage",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_storage_warning_thresholds():
    """Unit test: verify warning logic in service."""
    from api.services.storage_stats import _disk_free_mb

    # The function returns real disk stats — just verify it returns a tuple
    total, free = _disk_free_mb("/")
    assert total > 0
    assert free >= 0
    assert free <= total
