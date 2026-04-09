"""Filesystem event handler: receives file change events from the manager app.

Event types:
  created  → insert file + ingestion_state(DISCOVERED)
  modified → update content_hash, re-queue ingestion
  deleted  → set file.deleted_at
  renamed  → update file.path and file.filename

Full scan:
  Compare source path listing to files table.
  New files → created events.
  Missing files → deleted events.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.source import Source
from api.errors import NotFoundError

logger = structlog.get_logger()

EventType = Literal["created", "modified", "deleted", "renamed"]


async def _get_source(source_id: UUID, db: AsyncSession) -> Source:
    """Look up source by id; raise NotFoundError if missing or deleted."""
    stmt = select(Source).where(
        and_(Source.id == source_id, Source.deleted_at.is_(None))
    )
    result = await db.execute(stmt)
    source = result.scalar_one_or_none()
    if source is None:
        raise NotFoundError(
            error_code="SOURCE_NOT_FOUND",
            message=f"Source {source_id} not found.",
        )
    return source


async def handle_fs_event(
    *,
    source_id: UUID,
    event_type: EventType,
    path: str,
    old_path: str | None,
    db: AsyncSession,
) -> dict:
    """Process a single filesystem event.

    Returns a summary dict with the action taken.
    """
    source = await _get_source(source_id, db)

    if event_type == "created":
        return await _handle_created(source, path, db)
    elif event_type == "modified":
        return await _handle_modified(source, path, db)
    elif event_type == "deleted":
        return await _handle_deleted(source, path, db)
    elif event_type == "renamed":
        if not old_path:
            return {"action": "skipped", "reason": "rename requires old_path"}
        return await _handle_renamed(source, path, old_path, db)
    else:
        return {"action": "skipped", "reason": f"unknown event_type: {event_type}"}


async def _handle_created(source: Source, path: str, db: AsyncSession) -> dict:
    """Insert a new file record and queue it for ingestion."""
    # Check if file already exists (idempotent)
    stmt = select(File).where(
        and_(
            File.source_id == source.id,
            File.path == path,
            File.deleted_at.is_(None),
        )
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        logger.debug("fs_event_file_exists", path=path, file_id=str(existing.id))
        return {"action": "skipped", "reason": "file already exists", "file_id": str(existing.id)}

    filename = os.path.basename(path)
    file = File(
        workspace_id=source.workspace_id,
        source_id=source.id,
        filename=filename,
        path=path,
    )
    db.add(file)
    await db.flush()

    ingestion = IngestionState(
        file_id=file.id,
        workspace_id=source.workspace_id,
        current_stage="DISCOVERED",
    )
    db.add(ingestion)

    logger.info("fs_event_created", path=path, file_id=str(file.id))
    return {"action": "created", "file_id": str(file.id), "stage": "DISCOVERED"}


async def _handle_modified(source: Source, path: str, db: AsyncSession) -> dict:
    """Re-queue an existing file for ingestion (content changed)."""
    stmt = select(File).where(
        and_(
            File.source_id == source.id,
            File.path == path,
            File.deleted_at.is_(None),
        )
    )
    file = (await db.execute(stmt)).scalar_one_or_none()

    if file is None:
        # File doesn't exist yet — treat as created
        return await _handle_created(source, path, db)

    # Reset ingestion state to DISCOVERED
    stmt = (
        update(IngestionState)
        .where(IngestionState.file_id == file.id)
        .values(
            current_stage="DISCOVERED",
            error_message=None,
            retry_count=0,
        )
    )
    result = await db.execute(stmt)

    if result.rowcount == 0:
        # No ingestion state exists — create one
        db.add(IngestionState(
            file_id=file.id,
            workspace_id=source.workspace_id,
            current_stage="DISCOVERED",
        ))

    # Clear content hash so fingerprint stage recomputes it
    file.content_hash_sha256 = None

    logger.info("fs_event_modified", path=path, file_id=str(file.id))
    return {"action": "modified", "file_id": str(file.id), "stage": "DISCOVERED"}


async def _handle_deleted(source: Source, path: str, db: AsyncSession) -> dict:
    """Soft-delete a file."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(File)
        .where(
            and_(
                File.source_id == source.id,
                File.path == path,
                File.deleted_at.is_(None),
            )
        )
        .values(deleted_at=now)
    )
    result = await db.execute(stmt)

    if result.rowcount == 0:
        return {"action": "skipped", "reason": "file not found or already deleted"}

    logger.info("fs_event_deleted", path=path)
    return {"action": "deleted", "path": path}


async def _handle_renamed(
    source: Source, new_path: str, old_path: str, db: AsyncSession,
) -> dict:
    """Update the file path and filename."""
    stmt = select(File).where(
        and_(
            File.source_id == source.id,
            File.path == old_path,
            File.deleted_at.is_(None),
        )
    )
    file = (await db.execute(stmt)).scalar_one_or_none()

    if file is None:
        return {"action": "skipped", "reason": "original file not found"}

    file.path = new_path
    file.filename = os.path.basename(new_path)

    logger.info("fs_event_renamed", old_path=old_path, new_path=new_path, file_id=str(file.id))
    return {"action": "renamed", "file_id": str(file.id), "old_path": old_path, "new_path": new_path}


# ---------------------------------------------------------------------------
# Full scan
# ---------------------------------------------------------------------------


async def scan_source(
    *,
    source_id: UUID,
    db: AsyncSession,
) -> dict:
    """Compare filesystem listing to files table and reconcile.

    Returns a summary of new, deleted, and existing file counts.
    """
    source = await _get_source(source_id, db)

    if not source.path:
        return {
            "source_id": str(source_id),
            "error": "Source has no path configured",
            "new": 0,
            "deleted": 0,
            "existing": 0,
        }

    # Get current files in DB for this source
    stmt = select(File.path).where(
        and_(
            File.source_id == source.id,
            File.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    db_paths = {row[0] for row in result.all()}

    # Get files on disk
    disk_paths: set[str] = set()
    source_path = source.path

    if os.path.isdir(source_path):
        for root, _dirs, files in os.walk(source_path):
            for fname in files:
                # Skip hidden files and common system files
                if fname.startswith(".") or fname == "Thumbs.db" or fname == ".DS_Store":
                    continue
                disk_paths.add(os.path.join(root, fname))

    # Reconcile
    new_paths = disk_paths - db_paths
    deleted_paths = db_paths - disk_paths
    existing_paths = db_paths & disk_paths

    # Create new files
    for path in new_paths:
        await _handle_created(source, path, db)

    # Mark deleted files
    now = datetime.now(timezone.utc)
    if deleted_paths:
        stmt = (
            update(File)
            .where(
                and_(
                    File.source_id == source.id,
                    File.path.in_(deleted_paths),
                    File.deleted_at.is_(None),
                )
            )
            .values(deleted_at=now)
        )
        await db.execute(stmt)

    # Update last_sync_at
    source.last_sync_at = now

    logger.info(
        "fs_scan_completed",
        source_id=str(source_id),
        new=len(new_paths),
        deleted=len(deleted_paths),
        existing=len(existing_paths),
    )

    return {
        "source_id": str(source_id),
        "new": len(new_paths),
        "deleted": len(deleted_paths),
        "existing": len(existing_paths),
    }
