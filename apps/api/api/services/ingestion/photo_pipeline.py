"""Photo ingestion pipeline: DISCOVERED → COMPLETED (S08-001).

Entry point: ingest_photo(source_id, file_path, db)

Pipeline stages:
  DISCOVERED        → FINGERPRINTED   : SHA-256 hash + dedup check
  FINGERPRINTED     → METADATA_EXTRACTED : EXIF extraction + thumbnail + pHash → upsert photo_assets
  METADATA_EXTRACTED→ TEXT_EXTRACTED  : no-op (photos have no text)
  TEXT_EXTRACTED    → OCR_COMPLETED   : no-op
  OCR_COMPLETED     → EMBEDDING_QUEUED: no-op
  EMBEDDING_QUEUED  → EMBEDDED        : no-op
  EMBEDDED          → COMPLETED

CPU-bound extractor calls wrapped in asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.errors import NotFoundError
from api.services.ingestion.dedup import check_duplicate, compute_hash
from api.services.ingestion.photo_extractor import (
    PhotoMetadata,
    compute_perceptual_hash,
    extract_metadata,
    generate_thumbnail,
)
from api.services.ingestion.state_machine import advance_stage, fail_stage

logger = structlog.get_logger()

_PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".heic", ".heif"})

# Stages to advance through with no work (photos have no text/embeddings yet)
_NO_OP_STAGES = ["METADATA_EXTRACTED", "TEXT_EXTRACTED", "OCR_COMPLETED", "EMBEDDING_QUEUED"]


def _save_thumbnail_sync(thumb_bytes: bytes, workspace_id: UUID, photo_id: UUID) -> str:
    """Synchronous thumbnail save — call via asyncio.to_thread()."""
    base = Path(settings.THUMBNAIL_DIR)
    ws_dir = base / str(workspace_id)
    ws_dir.mkdir(parents=True, exist_ok=True)
    out_path = ws_dir / f"{photo_id}.jpg"
    out_path.write_bytes(thumb_bytes)
    return str(out_path.relative_to(base))


async def _save_thumbnail(thumb_bytes: bytes, workspace_id: UUID, photo_id: UUID) -> str:
    """Save thumbnail bytes to THUMBNAIL_DIR and return relative path."""
    return await asyncio.to_thread(_save_thumbnail_sync, thumb_bytes, workspace_id, photo_id)


async def ingest_photo(
    *,
    source_id: UUID,
    file_path: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Run the full photo ingestion pipeline for a single file.

    Returns a status dict: {status, file_id}.
    Raises NotFoundError if source_id is not found.
    """
    path = Path(file_path)

    # 1. Validate file extension
    if path.suffix.lower() not in _PHOTO_SUFFIXES:
        logger.info("photo_pipeline_unsupported", suffix=path.suffix)
        return {"status": "skipped_unsupported", "file_id": None}

    # 2. Load source
    src_result = await db.execute(
        select(Source).where(and_(Source.id == source_id, Source.deleted_at.is_(None)))
    )
    source = src_result.scalar_one_or_none()
    if source is None:
        raise NotFoundError(error_code="SOURCE_NOT_FOUND", message=f"Source {source_id} not found.")

    workspace_id = source.workspace_id

    # 3. Look up or create File row
    file_result = await db.execute(
        select(File).where(
            and_(
                File.source_id == source_id,
                File.workspace_id == workspace_id,
                File.path == file_path,
                File.deleted_at.is_(None),
            )
        )
    )
    file_row = file_result.scalar_one_or_none()

    if file_row is None:
        mime_type, _ = mimetypes.guess_type(file_path)
        file_row = File(
            workspace_id=workspace_id,
            source_id=source_id,
            filename=path.name,
            path=file_path,
            mime_type=mime_type or "image/jpeg",
            size_bytes=path.stat().st_size if path.exists() else None,
        )
        db.add(file_row)
        await db.flush()  # populate file_row.id

    # 4. Look up or create IngestionState
    state_result = await db.execute(
        select(IngestionState).where(IngestionState.file_id == file_row.id)
    )
    state = state_result.scalar_one_or_none()

    if state is None:
        state = IngestionState(
            file_id=file_row.id,
            workspace_id=workspace_id,
            current_stage="DISCOVERED",
            stages_completed=[],
        )
        db.add(state)
        await db.flush()

    file_id = file_row.id

    # ── Stage: DISCOVERED → FINGERPRINTED ──────────────────────────────────
    if state.current_stage == "DISCOVERED":
        content_hash = await asyncio.to_thread(compute_hash, file_path)
        duplicate = await check_duplicate(content_hash, workspace_id, db, exclude_file_id=file_id)
        if duplicate is not None:
            file_row.is_duplicate = True
            file_row.duplicate_of_id = duplicate.id
            file_row.content_hash_sha256 = content_hash
            await db.commit()
            logger.info("photo_pipeline_duplicate", file_id=str(file_id))
            return {"status": "duplicate_skipped", "file_id": str(file_id)}

        file_row.content_hash_sha256 = content_hash
        await advance_stage(file_id, "DISCOVERED", db)
        # After advance_stage, DB stage = FINGERPRINTED.
        # Re-fetch to get the updated stage for subsequent guards.
        state_r = await db.execute(select(IngestionState).where(IngestionState.file_id == file_id))
        state = state_r.scalar_one_or_none() or state

    # ── Stage: FINGERPRINTED → METADATA_EXTRACTED ──────────────────────────
    if state.current_stage == "FINGERPRINTED":
        try:
            meta: PhotoMetadata = await asyncio.to_thread(extract_metadata, path)
            thumb_bytes: bytes = await asyncio.to_thread(generate_thumbnail, path)
            phash: str = await asyncio.to_thread(compute_perceptual_hash, path)
        except Exception as exc:
            await fail_stage(file_id, "FINGERPRINTED", type(exc).__name__, db)
            logger.error("photo_pipeline_extraction_failed", file_id=str(file_id), exc_info=True)
            return {"status": "failed", "file_id": str(file_id)}

        thumbnail_rel = await _save_thumbnail(thumb_bytes, workspace_id, file_id)

        photo_asset = PhotoAsset(
            file_id=file_id,
            workspace_id=workspace_id,
            taken_at=meta.taken_at,
            gps_lat=meta.gps_lat,
            gps_lon=meta.gps_lon,
            location_name=meta.location_name,
            camera_make=meta.camera_make,
            camera_model=meta.camera_model,
            width=meta.width,
            height=meta.height,
            orientation=meta.orientation,
            thumbnail_path=thumbnail_rel,
            perceptual_hash=phash,
            exif_json=meta.exif_json,
        )
        db.add(photo_asset)
        await advance_stage(file_id, "FINGERPRINTED", db)

    # ── No-op stages: METADATA_EXTRACTED through EMBEDDING_QUEUED ──────────
    # Re-fetch state once, then advance through no-op stages sequentially.
    state_r = await db.execute(select(IngestionState).where(IngestionState.file_id == file_id))
    refreshed = state_r.scalar_one_or_none()
    if refreshed:
        for no_op_stage in _NO_OP_STAGES:
            if refreshed.current_stage == no_op_stage:
                await advance_stage(file_id, no_op_stage, db)
                # Advance doesn't update refreshed; but next iteration checks
                # the same starting point. These are one-shot — only one will match.

    # ── Stage: EMBEDDED → COMPLETED ────────────────────────────────────────
    state_r = await db.execute(select(IngestionState).where(IngestionState.file_id == file_id))
    refreshed = state_r.scalar_one_or_none()
    if refreshed and refreshed.current_stage == "EMBEDDED":
        await advance_stage(file_id, "EMBEDDED", db)

    await db.commit()
    logger.info("photo_pipeline_complete", file_id=str(file_id))
    return {"status": "completed", "file_id": str(file_id)}
