"""Phase 2 end-to-end integration test suite (S10-003).

Eight scenarios exercising the Phase 2 features: document ingestion,
semantic search, LLM grounded QA, photo pipeline, dedup, backup, and
graceful degradation when Ollama is unavailable.

Requires: PostgreSQL + Redis running (use ``make test-integration``).

These tests mock external services (Paperless, Ollama, Qdrant) at the
httpx / client level to keep them fast and deterministic while still
exercising the full request → service → DB path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.errors import ServiceUnavailableError
from api.services.auth import hash_password

# All tests share the session event loop for Redis pool compat
pytestmark = pytest.mark.asyncio(loop_scope="session")


# ── Shared helpers ──────────────────────────────────────────────────────────


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _csrf_headers(access_token: str, csrf_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-CSRF-Token": csrf_token,
    }


def _csrf_cookies(csrf_token: str) -> dict[str, str]:
    return {"ekamcore_csrf": csrf_token}


async def _create_user_and_workspace(
    test_session_factory, *, role: str = "admin"
) -> dict:
    """Create a fresh user + personal workspace. Returns credentials dict."""
    email = f"e2e-{uuid4().hex[:8]}@ekamcore.dev"
    password = "testpassword123"
    async with test_session_factory() as db:
        user = User(
            email=email,
            display_name="E2E User",
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        workspace = Workspace(
            name=f"WS-{uuid4().hex[:6]}",
            type="personal",
            owner_id=user.id,
        )
        db.add(workspace)
        await db.flush()
        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="admin",
        )
        db.add(member)
        await db.commit()
        user_id = user.id
        workspace_id = workspace.id
    return {
        "email": email,
        "password": password,
        "user_id": user_id,
        "workspace_id": workspace_id,
    }


async def _login(client: AsyncClient, creds: dict) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_cookie": resp.cookies.get("ekamcore_refresh"),
        "csrf_token": resp.cookies.get("ekamcore_csrf"),
        **creds,
    }


async def _create_source(
    test_session_factory, workspace_id: UUID, user_id: UUID, source_type: str
) -> UUID:
    """Create a source directly in DB and return its ID."""
    async with test_session_factory() as db:
        source = Source(
            workspace_id=workspace_id,
            name=f"E2E {source_type} {uuid4().hex[:6]}",
            type=source_type,
            path="/tmp/e2e-test",
            registered_by=user_id,
        )
        db.add(source)
        await db.commit()
        return source.id


async def _create_file(
    test_session_factory,
    workspace_id: UUID,
    source_id: UUID,
    filename: str,
    *,
    content_hash: str | None = None,
    mime_type: str = "application/pdf",
) -> UUID:
    """Create a file row directly in DB."""
    async with test_session_factory() as db:
        f = File(
            workspace_id=workspace_id,
            source_id=source_id,
            filename=filename,
            path=f"/tmp/e2e-test/{filename}",
            size_bytes=1024,
            mime_type=mime_type,
            content_hash_sha256=content_hash or uuid4().hex,
        )
        db.add(f)
        await db.commit()
        return f.id


async def _create_ingestion_state(
    test_session_factory,
    file_id: UUID,
    workspace_id: UUID,
    stage: str = "COMPLETED",
    stages_completed: list[str] | None = None,
) -> UUID:
    """Create an ingestion state row."""
    async with test_session_factory() as db:
        state = IngestionState(
            file_id=file_id,
            workspace_id=workspace_id,
            current_stage=stage,
            stages_completed=stages_completed or [],
        )
        db.add(state)
        await db.commit()
        return state.id


# ── 1. Document ingestion flow ──────────────────────────────────────────────


async def test_document_ingestion_flow(client, test_session_factory):
    """Sync a Paperless document → verify file row created via service layer."""
    creds = await _create_user_and_workspace(test_session_factory)
    ws_id = creds["workspace_id"]

    # Use the real Pydantic model so fields like .content work correctly
    from api.services.paperless.models import PaperlessDocument

    mock_content = "Total amount due: $5,000 for Q1 2026 services rendered."
    mock_doc = PaperlessDocument(
        id=1,
        title="EkamCore Test Invoice",
        content=mock_content,
        original_file_name="test-invoice.pdf",
        created=datetime(2026, 4, 10, tzinfo=timezone.utc),
        modified=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    async def _mock_list_docs_since(since):
        yield mock_doc

    mock_client = MagicMock()
    mock_client.get_document_content = AsyncMock(return_value=mock_content)
    mock_client.list_documents_modified_since = _mock_list_docs_since

    mock_embed = AsyncMock(return_value=[0.1] * 384)
    mock_qdrant = AsyncMock()
    mock_qdrant.upsert = AsyncMock()

    # Call sync_all_documents directly (not via HTTP, since 202 is async)
    from api.services.paperless.sync import sync_all_documents

    with (
        patch("api.services.paperless.sync.get_paperless_client", return_value=mock_client),
        patch("api.services.paperless.sync.generate_embedding", mock_embed),
        patch("api.services.paperless.sync.get_qdrant", return_value=mock_qdrant),
    ):
        async with test_session_factory() as db:
            result = await sync_all_documents(workspace_id=ws_id, db=db)

    assert result["synced"] >= 1, f"Expected >= 1 synced, got {result}"

    # Verify file row exists
    from sqlalchemy import select

    async with test_session_factory() as db:
        stmt = select(File).where(
            File.workspace_id == ws_id,
            File.filename == "test-invoice.pdf",
        )
        files = (await db.execute(stmt)).scalars().all()
        assert len(files) >= 1, "File row not created after sync"


# ── 2. Semantic search workspace isolation ──────────────────────────────────


async def test_semantic_search_workspace_isolation(client, test_session_factory):
    """Workspace access control: user B cannot query workspace A."""
    creds_a = await _create_user_and_workspace(test_session_factory)
    creds_b = await _create_user_and_workspace(test_session_factory)
    tokens_a = await _login(client, creds_a)
    tokens_b = await _login(client, creds_b)

    ws_a = creds_a["workspace_id"]
    ws_b = creds_b["workspace_id"]

    # User B tries to query workspace A → 403
    resp = await client.get(
        f"/api/v1/search?q=test&workspace_id={ws_a}",
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "WORKSPACE_ACCESS_DENIED"

    # User A queries their own workspace → 200
    resp = await client.get(
        f"/api/v1/search?q=test&workspace_id={ws_a}",
        headers=_auth_headers(tokens_a["access_token"]),
    )
    assert resp.status_code == 200

    # User B queries their own workspace → 200 (not leaking A's data)
    resp = await client.get(
        f"/api/v1/search?q=test&workspace_id={ws_b}",
        headers=_auth_headers(tokens_b["access_token"]),
    )
    assert resp.status_code == 200


# ── 3. LLM grounded QA ─────���───────────────────────────────────────────────


async def test_llm_grounded_qa(client, test_session_factory):
    """Query with context → LLM returns grounded answer citing sources."""
    creds = await _create_user_and_workspace(test_session_factory)
    tokens = await _login(client, creds)
    ws_id = creds["workspace_id"]

    # Create a file that search will find
    src = await _create_source(test_session_factory, ws_id, creds["user_id"], "paperless")
    file_id = await _create_file(test_session_factory, ws_id, src, "q1-report.pdf")
    await _create_ingestion_state(test_session_factory, file_id, ws_id)

    # Mock search to return a file card, and LLM to return grounded answer
    from api.schemas.envelope import FileCard
    mock_card = FileCard(
        id=file_id,
        priority_score=0.9,
        payload={"filename": "q1-report.pdf", "snippet": "Revenue was $10M in Q1."},
    )

    llm_response = json.dumps({
        "answer": "Revenue was $10M in Q1. [Source: q1-report.pdf]",
        "sources_used": ["q1-report.pdf"],
        "confidence": "high",
        "needs_more_context": False,
    })

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", new_callable=AsyncMock) as mock_llm,
    ):
        mock_search.return_value = ([mock_card], {"file": 1})
        mock_llm.return_value = llm_response

        resp = await client.post(
            "/api/v1/query",
            json={
                "query": "what was the revenue in Q1",
                "workspace_id": str(ws_id),
            },
            headers=_auth_headers(tokens["access_token"]),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer_text"] is not None
    assert "10M" in data["answer_text"]
    assert data["confidence_level"] == "high"
    assert data["metadata"]["query_path"] == "small_model"
    assert len(data["sources"]) >= 1
    assert data["sources"][0]["title"] == "q1-report.pdf"


# ── 4. LLM hallucination prevention ────��───────────────────────────────────


async def test_llm_hallucination_prevention(client, test_session_factory):
    """Query about something not in context → low confidence, no sources."""
    creds = await _create_user_and_workspace(test_session_factory)
    tokens = await _login(client, creds)
    ws_id = creds["workspace_id"]

    from api.schemas.envelope import FileCard
    mock_card = FileCard(
        id=uuid4(),
        priority_score=0.9,
        payload={"filename": "readme.txt", "snippet": "Project documentation."},
    )

    llm_response = json.dumps({
        "answer": "I don't have enough information to answer that.",
        "sources_used": [],
        "confidence": "low",
        "needs_more_context": True,
    })

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", new_callable=AsyncMock) as mock_llm,
    ):
        mock_search.return_value = ([mock_card], {"file": 1})
        mock_llm.return_value = llm_response

        resp = await client.post(
            "/api/v1/query",
            json={
                "query": "what is the secret password",
                "workspace_id": str(ws_id),
            },
            headers=_auth_headers(tokens["access_token"]),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "don" in data["answer_text"].lower() or "information" in data["answer_text"].lower()
    assert data["confidence_level"] == "low"
    assert len(data["sources"]) == 0


# ── 5. Photo pipeline ───��──────────────────────────────────────────────────


async def test_photo_pipeline(client, test_session_factory):
    """Ingest a photo → verify photo_assets entry with GPS and thumbnail."""
    creds = await _create_user_and_workspace(test_session_factory)
    tokens = await _login(client, creds)
    ws_id = creds["workspace_id"]

    src_id = await _create_source(
        test_session_factory, ws_id, creds["user_id"], "photo_folder"
    )

    # Create file + photo_asset directly to simulate pipeline completion
    file_id = await _create_file(
        test_session_factory, ws_id, src_id, "beach.jpg", mime_type="image/jpeg"
    )
    await _create_ingestion_state(test_session_factory, file_id, ws_id)

    async with test_session_factory() as db:
        photo = PhotoAsset(
            file_id=file_id,
            workspace_id=ws_id,
            taken_at=datetime(2026, 4, 10, 14, 30),
            gps_lat=37.775,
            gps_lon=-122.425,
            location_name="San Francisco, California, US",
            camera_make="Apple",
            camera_model="iPhone 15 Pro",
            width=4032,
            height=3024,
            orientation=1,
            thumbnail_path=f"{ws_id}/{file_id}.jpg",
            perceptual_hash="8000000000000000",
        )
        db.add(photo)
        await db.commit()

    # Search by location
    resp = await client.get(
        f"/api/v1/search?q=San+Francisco&type=photo&workspace_id={ws_id}",
        headers=_auth_headers(tokens["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["facets"].get("photo", 0) >= 1
    photo_results = [c for c in data["data"] if c["type"] == "photo"]
    assert len(photo_results) >= 1
    assert "San Francisco" in str(photo_results[0]["payload"])


# ── 6. Duplicate detection ──────────────────────────────────────────────────


async def test_duplicate_detection(client, test_session_factory):
    """Two files with same SHA-256 hash → second detected as duplicate."""
    creds = await _create_user_and_workspace(test_session_factory)
    ws_id = creds["workspace_id"]

    src = await _create_source(test_session_factory, ws_id, creds["user_id"], "local_folder")
    same_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"

    # Create original file
    file_1 = await _create_file(
        test_session_factory, ws_id, src, "original.pdf", content_hash=same_hash
    )

    # Try dedup check
    from api.services.ingestion.dedup import check_duplicate

    async with test_session_factory() as db:
        dup = await check_duplicate(same_hash, ws_id, db, exclude_file_id=None)
        assert dup is not None, "Duplicate should be detected"
        assert dup.id == file_1


# ── 7. Backup creates all components ────────────────────────────────────────


async def test_backup_rotation_logic(test_session_factory):
    """Verify the backup rotation logic identifies backups correctly.

    Tests the pure Python rotation module rather than the full shell script
    (which requires Docker).
    """
    import importlib.util
    import tempfile
    import shutil

    # Verify pipeline stages are complete and ordered
    from api.services.ingestion.state_machine import PIPELINE_STAGES
    assert PIPELINE_STAGES[0] == "DISCOVERED"
    assert PIPELINE_STAGES[-1] == "COMPLETED"
    assert len(PIPELINE_STAGES) == 9  # S11-006 added FACE_DETECTION

    # Import rotate.py from infra/backup using spec loader
    rotate_path = Path(__file__).resolve().parents[4] / "infra" / "backup" / "rotate.py"
    spec = importlib.util.spec_from_file_location("rotate", rotate_path)
    rotate_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rotate_mod)

    tmpdir = Path(tempfile.mkdtemp())
    try:
        for name in [
            "2026-04-01_00-00-00",
            "2026-04-02_00-00-00",
            "2026-04-03_00-00-00",
        ]:
            (tmpdir / name).mkdir()

        result = rotate_mod.rotate_backups(tmpdir, dry_run=True)
        assert isinstance(result, dict)
        assert result["kept_daily"] >= 1
        assert result["deleted"] == 0  # dry_run doesn't delete
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ��─ 8. Ollama down → graceful degradation ───────────────────────────────────


async def test_ollama_down_graceful_degradation(client, test_session_factory):
    """When LLM is unavailable, queries return search results with is_partial=true."""
    creds = await _create_user_and_workspace(test_session_factory)
    tokens = await _login(client, creds)
    ws_id = creds["workspace_id"]

    from api.schemas.envelope import FileCard
    mock_card = FileCard(
        id=uuid4(),
        priority_score=0.9,
        payload={"filename": "doc.pdf", "snippet": "Some content."},
    )

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch(
            "api.routers.query.call_llm",
            new_callable=AsyncMock,
            side_effect=ServiceUnavailableError(
                error_code="LLM_UNAVAILABLE",
                message="Ollama is unreachable.",
            ),
        ),
    ):
        mock_search.return_value = ([mock_card], {"file": 1})

        resp = await client.post(
            "/api/v1/query",
            json={
                "query": "tell me about the project status",
                "workspace_id": str(ws_id),
            },
            headers=_auth_headers(tokens["access_token"]),
        )

    assert resp.status_code == 200
    data = resp.json()
    # LLM failed → search fallback with is_partial
    assert data["answer_text"] is None
    assert data["metadata"]["is_partial"] is True
    assert len(data["cards"]) >= 1
    # User should still get useful results
    assert data["cards"][0]["type"] == "file"
