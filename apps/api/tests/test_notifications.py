"""Tests for G-09: Notification API.

Covers: create, list, mark-read, mark-all-read, unread count, auth.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from api.db.models.notification import Notification
from api.services.notification_service import (
    NotificationType,
    create_notification,
    get_notifications,
    get_unread_count,
    mark_all_read,
    mark_read,
)


# ── Service unit tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_notification(test_session_factory, seed_user):
    async with test_session_factory() as db:
        n = await create_notification(
            user_id=seed_user["user_id"],
            workspace_id=seed_user["workspace_id"],
            type=NotificationType.BACKUP_COMPLETE,
            title="Backup done",
            message="Daily backup completed.",
            db=db,
        )
        await db.commit()
        assert n.id is not None
        assert n.is_read is False
        assert n.type == "BACKUP_COMPLETE"


@pytest.mark.asyncio
async def test_get_unread_count(test_session_factory, seed_user):
    async with test_session_factory() as db:
        await create_notification(
            user_id=seed_user["user_id"],
            workspace_id=seed_user["workspace_id"],
            type=NotificationType.INGESTION_COMPLETE,
            title="Files processed",
            message="3 files ingested.",
            db=db,
        )
        await db.flush()
        count = await get_unread_count(seed_user["user_id"], seed_user["workspace_id"], db)
        assert count >= 1


@pytest.mark.asyncio
async def test_mark_read(test_session_factory, seed_user):
    async with test_session_factory() as db:
        n = await create_notification(
            user_id=seed_user["user_id"],
            workspace_id=seed_user["workspace_id"],
            type=NotificationType.SYSTEM_DEGRADED,
            title="AI unavailable",
            message="Ollama is down.",
            db=db,
        )
        await db.flush()
        result = await mark_read(n.id, seed_user["user_id"], db)
        assert result is True


@pytest.mark.asyncio
async def test_mark_all_read(test_session_factory, seed_user):
    async with test_session_factory() as db:
        for i in range(3):
            await create_notification(
                user_id=seed_user["user_id"],
                workspace_id=seed_user["workspace_id"],
                type=NotificationType.INGESTION_COMPLETE,
                title=f"Batch {i}",
                message=f"{i} files done.",
                db=db,
            )
        await db.flush()
        count = await mark_all_read(seed_user["user_id"], seed_user["workspace_id"], db)
        assert count >= 3


# ── API endpoint tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_notifications_endpoint(client, auth_tokens, test_session_factory):
    # Create a notification directly
    async with test_session_factory() as db:
        await create_notification(
            user_id=auth_tokens["user_id"],
            workspace_id=auth_tokens["workspace_id"],
            type=NotificationType.BACKUP_COMPLETE,
            title="Backup done",
            message="All good.",
            db=db,
        )
        await db.commit()

    resp = await client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "notifications" in data
    assert "unread_count" in data
    assert data["unread_count"] >= 1


@pytest.mark.asyncio
async def test_mark_read_endpoint(client, auth_tokens, test_session_factory):
    async with test_session_factory() as db:
        n = await create_notification(
            user_id=auth_tokens["user_id"],
            workspace_id=auth_tokens["workspace_id"],
            type=NotificationType.INGESTION_FAILED,
            title="Ingestion failed",
            message="2 files failed.",
            db=db,
        )
        await db.commit()
        nid = str(n.id)

    resp = await client.patch(
        f"/api/v1/notifications/{nid}/read",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "read"


@pytest.mark.asyncio
async def test_unread_filter(client, auth_tokens, test_session_factory):
    async with test_session_factory() as db:
        n = await create_notification(
            user_id=auth_tokens["user_id"],
            workspace_id=auth_tokens["workspace_id"],
            type=NotificationType.SYSTEM_RECOVERED,
            title="Back online",
            message="All services restored.",
            db=db,
        )
        await mark_read(n.id, auth_tokens["user_id"], db)
        await db.commit()

    resp = await client.get(
        "/api/v1/notifications?unread_only=true",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    # The one we just marked read should NOT appear
    data = resp.json()
    read_ids = [n["id"] for n in data["notifications"] if n["is_read"]]
    assert len(read_ids) == 0


@pytest.mark.asyncio
async def test_notifications_require_auth(client):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 401
