"""Tests for ingestion state machine (S02-003).

Verifies optimistic concurrency transitions, terminal stage protection,
failure handling with retry limits, and skip behavior.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.source import Source
from api.services.ingestion.state_machine import (
    MAX_RETRIES,
    PIPELINE_STAGES,
    advance_stage,
    fail_stage,
    skip_file,
)


async def _create_file_with_state(db: AsyncSession, seed_user: dict) -> dict:
    """Helper: create a source, file, and ingestion_state in the given session."""
    source = Source(
        workspace_id=seed_user["workspace_id"],
        name="Test Source",
        type="local_folder",
        path="/tmp/test",
        registered_by=seed_user["user_id"],
    )
    db.add(source)
    await db.flush()

    file = File(
        workspace_id=seed_user["workspace_id"],
        source_id=source.id,
        filename="test.txt",
        path="/tmp/test/test.txt",
    )
    db.add(file)
    await db.flush()

    state = IngestionState(
        file_id=file.id,
        workspace_id=seed_user["workspace_id"],
        current_stage="DISCOVERED",
    )
    db.add(state)
    await db.flush()

    return {"file_id": file.id, "workspace_id": seed_user["workspace_id"]}


@pytest.mark.asyncio
async def test_advance_through_full_pipeline(test_session_factory, seed_user: dict) -> None:
    """File should advance through every pipeline stage to COMPLETED."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)
        file_id = data["file_id"]

        for stage in PIPELINE_STAGES[:-1]:  # All except COMPLETED
            result = await advance_stage(file_id, stage, db)
            await db.flush()
            assert result is True, f"Failed to advance from {stage}"

        # Verify final state is COMPLETED
        stmt = select(IngestionState).where(IngestionState.file_id == file_id)
        row = (await db.execute(stmt)).scalars().first()
        assert row is not None
        assert row.current_stage == "COMPLETED"
        assert len(row.stages_completed) == len(PIPELINE_STAGES) - 1


@pytest.mark.asyncio
async def test_advance_idempotent_when_already_advanced(test_session_factory, seed_user: dict) -> None:
    """Advancing from an already-passed stage returns False (idempotent)."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)
        file_id = data["file_id"]

        # Advance DISCOVERED → FINGERPRINTED
        assert await advance_stage(file_id, "DISCOVERED", db) is True
        await db.flush()

        # Try advancing from DISCOVERED again — already at FINGERPRINTED
        assert await advance_stage(file_id, "DISCOVERED", db) is False


@pytest.mark.asyncio
async def test_advance_from_terminal_stage_returns_false(test_session_factory, seed_user: dict) -> None:
    """Cannot advance from COMPLETED, FAILED, or SKIPPED."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)
        file_id = data["file_id"]

        assert await advance_stage(file_id, "COMPLETED", db) is False
        assert await advance_stage(file_id, "FAILED", db) is False
        assert await advance_stage(file_id, "SKIPPED", db) is False


@pytest.mark.asyncio
async def test_fail_stage_transitions_to_failed(test_session_factory, seed_user: dict) -> None:
    """fail_stage should move file to FAILED with error message and increment retry_count."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)
        file_id = data["file_id"]

        result = await fail_stage(file_id, "DISCOVERED", "parse error", db)
        assert result is True
        await db.flush()

        stmt = select(IngestionState).where(IngestionState.file_id == file_id)
        row = (await db.execute(stmt)).scalars().first()
        assert row is not None
        assert row.current_stage == "FAILED"
        assert row.error_message == "parse error"
        assert row.retry_count == 1


@pytest.mark.asyncio
async def test_fail_stage_wrong_expected_returns_false(test_session_factory, seed_user: dict) -> None:
    """fail_stage with wrong expected stage returns False (optimistic concurrency)."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)
        file_id = data["file_id"]

        # File is at DISCOVERED, try failing from FINGERPRINTED
        result = await fail_stage(file_id, "FINGERPRINTED", "should not work", db)
        assert result is False


@pytest.mark.asyncio
async def test_fail_respects_max_retries(test_session_factory, seed_user: dict) -> None:
    """After MAX_RETRIES failures, fail_stage should return False."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)
        file_id = data["file_id"]

        # Manually set retry_count to MAX_RETRIES
        stmt = (
            update(IngestionState)
            .where(IngestionState.file_id == file_id)
            .values(retry_count=MAX_RETRIES)
        )
        await db.execute(stmt)
        await db.flush()

        result = await fail_stage(file_id, "DISCOVERED", "max retries hit", db)
        assert result is False


@pytest.mark.asyncio
async def test_skip_file_transitions_to_skipped(test_session_factory, seed_user: dict) -> None:
    """skip_file should move file to SKIPPED stage."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)
        file_id = data["file_id"]

        result = await skip_file(file_id, "DISCOVERED", db)
        assert result is True
        await db.flush()

        stmt = select(IngestionState).where(IngestionState.file_id == file_id)
        row = (await db.execute(stmt)).scalars().first()
        assert row is not None
        assert row.current_stage == "SKIPPED"


@pytest.mark.asyncio
async def test_skip_from_terminal_returns_false(test_session_factory, seed_user: dict) -> None:
    """Cannot skip a file already in a terminal stage."""
    async with test_session_factory() as db:
        data = await _create_file_with_state(db, seed_user)

        assert await skip_file(data["file_id"], "COMPLETED", db) is False
        assert await skip_file(data["file_id"], "FAILED", db) is False
        assert await skip_file(data["file_id"], "SKIPPED", db) is False
