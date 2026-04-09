"""Tests for S06-005: Filesystem event handling endpoints.

Covers:
  - Created event: inserts file + ingestion state
  - Modified event: resets ingestion state
  - Deleted event: soft-deletes file
  - Renamed event: updates path and filename
  - Idempotent: duplicate created events don't create duplicates
  - Source not found: returns 404
  - Full scan: reconciles filesystem vs database
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.source import Source
from api.services.ingestion.fs_handler import handle_fs_event, scan_source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_source(db: AsyncSession, seed_user: dict, path: str | None = None) -> Source:
    src = Source(
        workspace_id=seed_user["workspace_id"],
        name=f"FS Test Source {uuid4().hex[:6]}",
        type="local_folder",
        path=path,
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(src)
    await db.flush()
    return src


async def _make_file(
    db: AsyncSession, source: Source, path: str = "/test/file.txt",
) -> File:
    f = File(
        workspace_id=source.workspace_id,
        source_id=source.id,
        filename=os.path.basename(path),
        path=path,
    )
    db.add(f)
    await db.flush()
    return f


# ---------------------------------------------------------------------------
# Created event
# ---------------------------------------------------------------------------


class TestCreatedEvent:
    @pytest.mark.asyncio
    async def test_creates_file_and_ingestion_state(self, test_session_factory, seed_user):
        ws_id = seed_user["workspace_id"]
        unique_path = f"/docs/report_{uuid4().hex[:8]}.pdf"

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            source_id = src.id
            await db.commit()

        async with test_session_factory() as db:
            result = await handle_fs_event(
                source_id=source_id,
                event_type="created",
                path=unique_path,
                old_path=None,
                db=db,
            )
            await db.commit()

        assert result["action"] == "created"
        assert result["stage"] == "DISCOVERED"
        file_id = result["file_id"]

        # Verify file and ingestion state exist
        async with test_session_factory() as db:
            from uuid import UUID as UUIDType
            file_stmt = select(File).where(File.id == UUIDType(file_id))
            file = (await db.execute(file_stmt)).scalar_one()
            assert file.path == unique_path
            assert file.workspace_id == ws_id

            ing_stmt = select(IngestionState).where(IngestionState.file_id == file.id)
            ing = (await db.execute(ing_stmt)).scalar_one()
            assert ing.current_stage == "DISCOVERED"

    @pytest.mark.asyncio
    async def test_idempotent_created(self, test_session_factory, seed_user):
        """Duplicate created events should not create duplicate files."""
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            source_id = src.id
            await db.commit()

        async with test_session_factory() as db:
            r1 = await handle_fs_event(
                source_id=source_id, event_type="created",
                path="/docs/dup.txt", old_path=None, db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            r2 = await handle_fs_event(
                source_id=source_id, event_type="created",
                path="/docs/dup.txt", old_path=None, db=db,
            )

        assert r1["action"] == "created"
        assert r2["action"] == "skipped"


# ---------------------------------------------------------------------------
# Modified event
# ---------------------------------------------------------------------------


class TestModifiedEvent:
    @pytest.mark.asyncio
    async def test_resets_ingestion_state(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            f = await _make_file(db, src, "/docs/existing.txt")
            file_id = f.id
            db.add(IngestionState(
                file_id=f.id,
                workspace_id=src.workspace_id,
                current_stage="COMPLETED",
            ))
            source_id = src.id
            await db.commit()

        async with test_session_factory() as db:
            result = await handle_fs_event(
                source_id=source_id, event_type="modified",
                path="/docs/existing.txt", old_path=None, db=db,
            )
            await db.commit()

        assert result["action"] == "modified"
        assert result["stage"] == "DISCOVERED"

        async with test_session_factory() as db:
            ing = (await db.execute(
                select(IngestionState).where(IngestionState.file_id == file_id)
            )).scalar_one()
            assert ing.current_stage == "DISCOVERED"

    @pytest.mark.asyncio
    async def test_modified_nonexistent_creates(self, test_session_factory, seed_user):
        """Modified event for missing file should create it."""
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            source_id = src.id
            await db.commit()

        async with test_session_factory() as db:
            result = await handle_fs_event(
                source_id=source_id, event_type="modified",
                path="/docs/new_via_modify.txt", old_path=None, db=db,
            )
            await db.commit()

        assert result["action"] == "created"


# ---------------------------------------------------------------------------
# Deleted event
# ---------------------------------------------------------------------------


class TestDeletedEvent:
    @pytest.mark.asyncio
    async def test_soft_deletes_file(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            f = await _make_file(db, src, "/docs/to_delete.txt")
            source_id = src.id
            file_id = f.id
            await db.commit()

        async with test_session_factory() as db:
            result = await handle_fs_event(
                source_id=source_id, event_type="deleted",
                path="/docs/to_delete.txt", old_path=None, db=db,
            )
            await db.commit()

        assert result["action"] == "deleted"

        async with test_session_factory() as db:
            file = (await db.execute(select(File).where(File.id == file_id))).scalar_one()
            assert file.deleted_at is not None

    @pytest.mark.asyncio
    async def test_deleted_nonexistent_skips(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            source_id = src.id
            await db.commit()

        async with test_session_factory() as db:
            result = await handle_fs_event(
                source_id=source_id, event_type="deleted",
                path="/docs/ghost.txt", old_path=None, db=db,
            )

        assert result["action"] == "skipped"


# ---------------------------------------------------------------------------
# Renamed event
# ---------------------------------------------------------------------------


class TestRenamedEvent:
    @pytest.mark.asyncio
    async def test_updates_path_and_filename(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            f = await _make_file(db, src, "/docs/old_name.txt")
            source_id = src.id
            file_id = f.id
            await db.commit()

        async with test_session_factory() as db:
            result = await handle_fs_event(
                source_id=source_id, event_type="renamed",
                path="/docs/new_name.txt",
                old_path="/docs/old_name.txt",
                db=db,
            )
            await db.commit()

        assert result["action"] == "renamed"
        assert result["new_path"] == "/docs/new_name.txt"

        async with test_session_factory() as db:
            file = (await db.execute(select(File).where(File.id == file_id))).scalar_one()
            assert file.path == "/docs/new_name.txt"
            assert file.filename == "new_name.txt"

    @pytest.mark.asyncio
    async def test_rename_without_old_path_skips(self, test_session_factory, seed_user):
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user)
            source_id = src.id
            await db.commit()

        async with test_session_factory() as db:
            result = await handle_fs_event(
                source_id=source_id, event_type="renamed",
                path="/docs/new.txt", old_path=None, db=db,
            )

        assert result["action"] == "skipped"


# ---------------------------------------------------------------------------
# Source not found
# ---------------------------------------------------------------------------


class TestSourceNotFound:
    @pytest.mark.asyncio
    async def test_missing_source_raises_404(self, test_session_factory, seed_user):
        from api.errors import NotFoundError

        async with test_session_factory() as db:
            with pytest.raises(NotFoundError):
                await handle_fs_event(
                    source_id=uuid4(),
                    event_type="created",
                    path="/test.txt",
                    old_path=None,
                    db=db,
                )


# ---------------------------------------------------------------------------
# Full scan
# ---------------------------------------------------------------------------


class TestFsScan:
    @pytest.mark.asyncio
    async def test_scan_discovers_new_files(self, test_session_factory, seed_user):
        """Scan should create file records for files on disk not in DB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            open(os.path.join(tmpdir, "new1.txt"), "w").close()
            open(os.path.join(tmpdir, "new2.txt"), "w").close()
            open(os.path.join(tmpdir, ".hidden"), "w").close()  # should be skipped

            async with test_session_factory() as db:
                src = await _make_source(db, seed_user, path=tmpdir)
                source_id = src.id
                await db.commit()

            async with test_session_factory() as db:
                result = await scan_source(source_id=source_id, db=db)
                await db.commit()

        assert result["new"] == 2  # .hidden skipped
        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_scan_marks_deleted_files(self, test_session_factory, seed_user):
        """Files in DB but not on disk should be marked deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            async with test_session_factory() as db:
                src = await _make_source(db, seed_user, path=tmpdir)
                # Add a file to DB that doesn't exist on disk
                db.add(File(
                    workspace_id=src.workspace_id,
                    source_id=src.id,
                    filename="ghost.txt",
                    path=os.path.join(tmpdir, "ghost.txt"),
                ))
                source_id = src.id
                await db.commit()

            async with test_session_factory() as db:
                result = await scan_source(source_id=source_id, db=db)
                await db.commit()

        assert result["deleted"] == 1
        assert result["new"] == 0

    @pytest.mark.asyncio
    async def test_scan_no_path_returns_error(self, test_session_factory, seed_user):
        """Source without a path should return error."""
        async with test_session_factory() as db:
            src = await _make_source(db, seed_user, path=None)
            source_id = src.id
            await db.commit()

        async with test_session_factory() as db:
            result = await scan_source(source_id=source_id, db=db)

        assert "error" in result


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fs_event_endpoint(client, test_session_factory, seed_user):
    async with test_session_factory() as db:
        src = await _make_source(db, seed_user)
        source_id = src.id
        await db.commit()

    response = await client.post(
        "/api/v1/internal/fs-event",
        json={
            "source_id": str(source_id),
            "event_type": "created",
            "path": "/endpoint/test.txt",
        },
    )
    assert response.status_code == 202
    assert response.json()["action"] == "created"


@pytest.mark.asyncio
async def test_fs_scan_endpoint(client, test_session_factory, seed_user):
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "scan_test.txt"), "w").close()

        async with test_session_factory() as db:
            src = await _make_source(db, seed_user, path=tmpdir)
            source_id = src.id
            await db.commit()

        response = await client.post(
            "/api/v1/internal/fs-scan",
            json={"source_id": str(source_id)},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["new"] == 1
