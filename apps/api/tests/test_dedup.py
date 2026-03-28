"""Tests for SHA-256 deduplication service (S02-003).

Verifies hash computation and duplicate detection within workspaces.
"""

import tempfile
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File
from api.db.models.source import Source
from api.services.ingestion.dedup import (
    check_duplicate,
    compute_hash,
    compute_hash_from_bytes,
)


@pytest.mark.asyncio
async def test_compute_hash_from_file() -> None:
    """compute_hash should return consistent SHA-256 hex digest."""
    content = b"hello world test content"

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
        f.flush()
        path = f.name

    result = compute_hash(path)
    assert len(result) == 64
    assert result == compute_hash_from_bytes(content)


@pytest.mark.asyncio
async def test_compute_hash_deterministic() -> None:
    """Same content should always produce the same hash."""
    data = b"deterministic content"
    assert compute_hash_from_bytes(data) == compute_hash_from_bytes(data)


@pytest.mark.asyncio
async def test_different_content_different_hash() -> None:
    """Different content should produce different hashes."""
    hash1 = compute_hash_from_bytes(b"content A")
    hash2 = compute_hash_from_bytes(b"content B")
    assert hash1 != hash2


async def _create_file_with_hash(db: AsyncSession, seed_user: dict) -> dict:
    """Helper: create a source and file with a known content hash."""
    known_hash = compute_hash_from_bytes(b"known content for dedup test")

    source = Source(
        workspace_id=seed_user["workspace_id"],
        name="Dedup Source",
        type="local_folder",
        path="/tmp/dedup",
        registered_by=seed_user["user_id"],
    )
    db.add(source)
    await db.flush()

    file = File(
        workspace_id=seed_user["workspace_id"],
        source_id=source.id,
        filename="original.txt",
        path="/tmp/dedup/original.txt",
        content_hash_sha256=known_hash,
    )
    db.add(file)
    await db.flush()

    return {
        "file_id": file.id,
        "workspace_id": seed_user["workspace_id"],
        "content_hash": known_hash,
    }


@pytest.mark.asyncio
async def test_check_duplicate_finds_existing(test_session_factory, seed_user: dict) -> None:
    """check_duplicate should find an existing file with the same hash."""
    async with test_session_factory() as db:
        data = await _create_file_with_hash(db, seed_user)

        existing = await check_duplicate(data["content_hash"], data["workspace_id"], db)
        assert existing is not None
        assert existing.id == data["file_id"]


@pytest.mark.asyncio
async def test_check_duplicate_no_match(test_session_factory, seed_user: dict) -> None:
    """check_duplicate should return None when no file matches."""
    async with test_session_factory() as db:
        data = await _create_file_with_hash(db, seed_user)

        different_hash = compute_hash_from_bytes(b"completely different content")
        existing = await check_duplicate(different_hash, data["workspace_id"], db)
        assert existing is None


@pytest.mark.asyncio
async def test_check_duplicate_excludes_self(test_session_factory, seed_user: dict) -> None:
    """check_duplicate should exclude the file itself when exclude_file_id is set."""
    async with test_session_factory() as db:
        data = await _create_file_with_hash(db, seed_user)

        existing = await check_duplicate(
            data["content_hash"],
            data["workspace_id"],
            db,
            exclude_file_id=data["file_id"],
        )
        assert existing is None


@pytest.mark.asyncio
async def test_check_duplicate_workspace_isolation(test_session_factory, seed_user: dict) -> None:
    """check_duplicate should not find files from other workspaces."""
    async with test_session_factory() as db:
        data = await _create_file_with_hash(db, seed_user)

        other_workspace_id = uuid4()
        existing = await check_duplicate(data["content_hash"], other_workspace_id, db)
        assert existing is None
