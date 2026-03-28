"""SHA-256 content deduplication for ingested files.

Computes file hashes and checks for duplicates within a workspace.
"""

import hashlib
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File

logger = structlog.get_logger()

_CHUNK_SIZE = 65536  # 64 KB read chunks


def compute_hash(file_path: str | Path) -> str:
    """Compute SHA-256 hex digest for a file on disk."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


def compute_hash_from_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest from in-memory bytes."""
    return hashlib.sha256(data).hexdigest()


async def check_duplicate(
    content_hash: str,
    workspace_id: UUID,
    db: AsyncSession,
    exclude_file_id: UUID | None = None,
) -> File | None:
    """Check if a file with the same hash already exists in the workspace.

    Returns the existing File if a duplicate is found, None otherwise.
    """
    stmt = select(File).where(
        File.content_hash_sha256 == content_hash,
        File.workspace_id == workspace_id,
        File.deleted_at.is_(None),
        File.is_duplicate.is_(False),
    )
    if exclude_file_id is not None:
        stmt = stmt.where(File.id != exclude_file_id)

    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing:
        logger.info(
            "duplicate_detected",
            content_hash=content_hash,
            existing_file_id=str(existing.id),
            workspace_id=str(workspace_id),
        )

    return existing
