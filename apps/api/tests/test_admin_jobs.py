"""Tests for S09-003: Admin ingestion jobs endpoints.

Covers:
  - GET /api/v1/admin/jobs: job listing grouped by status
  - POST /api/v1/admin/jobs/:id/retry: retry a single failed job
  - POST /api/v1/admin/jobs/retry-all-failed: bulk retry
  - Auth: admin-only access, standard user gets 403
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.auth import hash_password


# ── Fixtures ──


@pytest_asyncio.fixture
async def admin_seed(test_session_factory):
    """Create an admin user with workspace."""
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

        return {
            "user_id": user.id,
            "email": email,
            "password": password,
            "workspace_id": workspace.id,
        }


@pytest_asyncio.fixture
async def admin_tokens(client, admin_seed):
    """Login as admin and return tokens."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_seed["email"], "password": admin_seed["password"]},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    return {
        "access_token": data["access_token"],
        **admin_seed,
    }


@pytest_asyncio.fixture
async def source_id(test_session_factory, admin_tokens):
    """Create a source for test files."""
    async with test_session_factory() as db:
        source = Source(
            workspace_id=admin_tokens["workspace_id"],
            name="Test Source",
            type="local_folder",
            path="/tmp/test",
            registered_by=admin_tokens["user_id"],
        )
        db.add(source)
        await db.commit()
        return source.id


@pytest_asyncio.fixture
async def ingestion_states(test_session_factory, admin_tokens, source_id):
    """Create 3 files with ingestion states: active, completed, failed."""
    async with test_session_factory() as db:
        files = []
        for name in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
            f = File(
                workspace_id=admin_tokens["workspace_id"],
                source_id=source_id,
                filename=name,
                path=f"/tmp/test/{name}",
                size_bytes=1024,
            )
            db.add(f)
            files.append(f)
        await db.flush()

        active = IngestionState(
            file_id=files[0].id,
            workspace_id=admin_tokens["workspace_id"],
            current_stage="TEXT_EXTRACTED",
            stages_completed=["DISCOVERED", "FINGERPRINTED", "METADATA_EXTRACTED"],
        )
        completed = IngestionState(
            file_id=files[1].id,
            workspace_id=admin_tokens["workspace_id"],
            current_stage="COMPLETED",
            stages_completed=["DISCOVERED", "FINGERPRINTED", "METADATA_EXTRACTED",
                              "TEXT_EXTRACTED", "OCR_COMPLETED", "EMBEDDING_QUEUED", "EMBEDDED"],
        )
        failed = IngestionState(
            file_id=files[2].id,
            workspace_id=admin_tokens["workspace_id"],
            current_stage="FAILED",
            stages_completed=["DISCOVERED"],
            error_message="OCR engine crashed",
            retry_count=1,
        )
        db.add_all([active, completed, failed])
        await db.commit()

        return {
            "active": active,
            "completed": completed,
            "failed": failed,
        }


# ── Tests ──


@pytest.mark.asyncio
async def test_list_jobs_returns_grouped_results(client, admin_tokens, ingestion_states):
    response = await client.get(
        "/api/v1/admin/jobs",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data["active"]) >= 1
    active_filenames = [j["filename"] for j in data["active"]]
    assert "doc1.pdf" in active_filenames

    assert len(data["recently_completed"]) >= 1
    completed_filenames = [j["filename"] for j in data["recently_completed"]]
    assert "doc2.pdf" in completed_filenames

    assert len(data["failed"]) >= 1
    failed_jobs = [j for j in data["failed"] if j["filename"] == "doc3.pdf"]
    assert len(failed_jobs) == 1
    assert failed_jobs[0]["error_message"] == "OCR engine crashed"
    assert failed_jobs[0]["retry_count"] == 1


@pytest.mark.asyncio
async def test_list_jobs_includes_source_name(client, admin_tokens, ingestion_states):
    response = await client.get(
        "/api/v1/admin/jobs",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    data = response.json()
    active_jobs = [j for j in data["active"] if j["filename"] == "doc1.pdf"]
    assert active_jobs[0]["source_name"] == "Test Source"


@pytest.mark.asyncio
async def test_retry_single_job_resets_to_discovered(client, admin_tokens, ingestion_states, test_session_factory):
    failed_id = str(ingestion_states["failed"].id)

    response = await client.post(
        f"/api/v1/admin/jobs/{failed_id}/retry",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "retry_queued"

    # Verify the state was reset
    async with test_session_factory() as db:
        stmt = select(IngestionState).where(IngestionState.id == ingestion_states["failed"].id)
        row = (await db.execute(stmt)).scalar_one()
        assert row.current_stage == "DISCOVERED"
        assert row.error_message is None
        assert row.stages_completed == []


@pytest.mark.asyncio
async def test_retry_non_failed_job_returns_404(client, admin_tokens, ingestion_states):
    active_id = str(ingestion_states["active"].id)

    response = await client.post(
        f"/api/v1/admin/jobs/{active_id}/retry",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_all_failed_resets_all(client, admin_tokens, ingestion_states, test_session_factory):
    response = await client.post(
        "/api/v1/admin/jobs/retry-all-failed",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["count"] >= 1

    # Verify reset
    async with test_session_factory() as db:
        stmt = select(IngestionState).where(IngestionState.id == ingestion_states["failed"].id)
        row = (await db.execute(stmt)).scalar_one()
        assert row.current_stage == "DISCOVERED"


@pytest.mark.asyncio
async def test_jobs_requires_admin_role(client, auth_tokens):
    """Standard (non-admin) user gets 403."""
    response = await client.get(
        "/api/v1/admin/jobs",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403
