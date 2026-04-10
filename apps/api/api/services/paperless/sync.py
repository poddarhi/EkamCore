"""PaperlessNGX document sync worker (S07-002).

Incrementally syncs Paperless documents into EkamCore:

  1. Reads the last-sync cursor from the ``settings`` table.
  2. Pages through documents modified after that cursor via PaperlessClient.
  3. For each document:
       a. Upserts a ``files`` row (SHA-256 of content text for dedup).
       b. Creates / advances ``ingestion_states`` straight to TEXT_EXTRACTED
          (Paperless already did OCR — intermediate pipeline stages are no-ops).
       c. Chunks the text and generates embeddings (P3 resource slot).
       d. Writes ``file_chunks`` rows and upserts into Qdrant
          ``document_embeddings`` collection.
       e. Advances the ingestion state to COMPLETED.
  4. Updates the cursor to ``datetime.now(UTC)``.

Errors are isolated per document — one failure never blocks the rest of the
sync run.  The Qdrant point ID equals ``str(chunk.id)`` (UUID v7).
"""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from qdrant_client.models import PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File
from api.db.models.file_chunk import FileChunk
from api.db.models.ingestion_state import IngestionState
from api.db.models.setting import Setting
from api.db.models.source import Source
from api.db.models.workspace import Workspace
from api.errors import ServiceUnavailableError
from api.services.ingestion.chunker import chunk_text
from api.services.ingestion.embedder import EmbeddingInput, generate_embedding
from api.services.ingestion.state_machine import (
    PIPELINE_STAGES,
    advance_stage,
    fail_stage,
)
from api.services.paperless.client import get_paperless_client
from api.services.paperless.models import PaperlessDocument
from api.services.qdrant_client import get_qdrant
from api.services.resource_controller import Priority, acquire_slot

logger = structlog.get_logger()

_SETTINGS_NS = "paperless"
_SETTINGS_KEY = "last_sync_at"
_PAPERLESS_SOURCE_TYPE = "paperless"
_PAPERLESS_SOURCE_NAME = "PaperlessNGX"

# Stages to skip through when Paperless already extracted text
_SKIP_TO_TEXT_EXTRACTED = PIPELINE_STAGES[
    PIPELINE_STAGES.index("DISCOVERED"): PIPELINE_STAGES.index("TEXT_EXTRACTED")
]

# Stages to advance through after embedding
_EMBED_TO_COMPLETED = PIPELINE_STAGES[
    PIPELINE_STAGES.index("TEXT_EXTRACTED"): PIPELINE_STAGES.index("COMPLETED")
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _content_hash(text: str) -> str:
    """SHA-256 of the OCR text content.  Lighter than downloading the PDF."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _infer_mime(filename: str | None) -> str:
    if not filename:
        return "application/octet-stream"
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


async def _get_or_create_source(workspace_id: UUID, owner_id: UUID, db: AsyncSession) -> UUID:
    """Return the UUID of the workspace's Paperless source, creating it if absent."""
    stmt = select(Source).where(
        Source.workspace_id == workspace_id,
        Source.type == _PAPERLESS_SOURCE_TYPE,
        Source.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return existing.id

    source = Source(
        workspace_id=workspace_id,
        name=_PAPERLESS_SOURCE_NAME,
        type=_PAPERLESS_SOURCE_TYPE,
        status="active",
        registered_by=owner_id,
    )
    db.add(source)
    await db.flush()
    logger.info("paperless_source_created", workspace_id=str(workspace_id))
    return source.id


async def _get_last_sync_at(workspace_id: UUID, db: AsyncSession) -> datetime:
    """Return the last successful sync timestamp, or the Unix epoch if never synced."""
    stmt = select(Setting).where(
        Setting.workspace_id == workspace_id,
        Setting.user_id.is_(None),
        Setting.namespace == _SETTINGS_NS,
        Setting.key == _SETTINGS_KEY,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row and row.value_json and "iso" in row.value_json:
        return datetime.fromisoformat(row.value_json["iso"])
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


async def _set_last_sync_at(workspace_id: UUID, ts: datetime, db: AsyncSession) -> None:
    """Upsert the last_sync_at cursor for the workspace."""
    stmt = select(Setting).where(
        Setting.workspace_id == workspace_id,
        Setting.user_id.is_(None),
        Setting.namespace == _SETTINGS_NS,
        Setting.key == _SETTINGS_KEY,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        row.value_json = {"iso": ts.isoformat()}
    else:
        db.add(Setting(
            workspace_id=workspace_id,
            user_id=None,
            namespace=_SETTINGS_NS,
            key=_SETTINGS_KEY,
            value_json={"iso": ts.isoformat()},
        ))


async def _advance_stages(file_id: UUID, stages: list[str], db: AsyncSession) -> None:
    """Advance through a sequence of stages (each must be the expected_stage)."""
    for stage in stages:
        await advance_stage(file_id, stage, db)
        await db.flush()


async def _upsert_file(
    workspace_id: UUID,
    source_id: UUID,
    doc: PaperlessDocument,
    db: AsyncSession,
) -> tuple[File, bool]:
    """Upsert a File row for a Paperless document.

    Returns (file, is_new) where is_new=True means the row was just inserted.
    """
    path = f"paperless://documents/{doc.id}"
    stmt = select(File).where(
        File.workspace_id == workspace_id,
        File.path == path,
        File.deleted_at.is_(None),
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    ch = _content_hash(doc.content)
    metadata: dict[str, Any] = {
        "paperless_id": doc.id,
        "correspondent_id": doc.correspondent_id,
        "tag_ids": doc.tag_ids,
        "document_type_id": doc.document_type_id,
    }
    mime = _infer_mime(doc.original_file_name)

    if existing:
        existing.content_hash_sha256 = ch
        existing.metadata_json = metadata
        existing.mime_type = mime
        return existing, False

    file = File(
        workspace_id=workspace_id,
        source_id=source_id,
        filename=doc.original_file_name or f"paperless-{doc.id}.pdf",
        path=path,
        content_hash_sha256=ch,
        mime_type=mime,
        metadata_json=metadata,
        is_duplicate=False,
    )
    db.add(file)
    await db.flush()
    return file, True


async def _create_ingestion_state_if_new(
    file_id: UUID, workspace_id: UUID, db: AsyncSession
) -> bool:
    """Insert an IngestionState at DISCOVERED if one does not exist.

    Returns True if a new row was created.
    """
    stmt = select(IngestionState).where(IngestionState.file_id == file_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return False

    db.add(IngestionState(
        file_id=file_id,
        workspace_id=workspace_id,
        current_stage="DISCOVERED",
        stages_completed=[],
        retry_count=0,
    ))
    await db.flush()
    return True


async def _delete_old_chunks(file_id: UUID, workspace_id: UUID, db: AsyncSession) -> None:
    """Remove existing chunks for a file before re-ingesting."""
    stmt = select(FileChunk).where(
        FileChunk.file_id == file_id,
        FileChunk.workspace_id == workspace_id,
    )
    rows = (await db.execute(stmt)).scalars().all()
    for row in rows:
        await db.delete(row)
    if rows:
        await db.flush()


async def _embed_and_store(
    file: File,
    workspace_id: UUID,
    source_id: UUID,
    doc: PaperlessDocument,
    db: AsyncSession,
) -> int:
    """Chunk text, embed each chunk, write to Qdrant + file_chunks table.

    Returns the number of chunks stored.
    """
    await _delete_old_chunks(file.id, workspace_id, db)

    content = doc.content
    if not content.strip():
        logger.info("paperless_doc_empty_content", paperless_id=doc.id)
        return 0

    chunks = chunk_text(content, max_tokens=500, overlap=50)
    if not chunks:
        return 0

    filename = doc.original_file_name or ""
    mime = _infer_mime(filename)
    qdrant = get_qdrant()
    points: list[PointStruct] = []

    for idx, chunk in enumerate(chunks):
        async with acquire_slot(Priority.P3_BACKGROUND_IMPORTANT):
            vector = await generate_embedding(
                text=chunk.text,
                filename=filename,
                mime_type=mime,
            )

        # Persist chunk metadata to PG
        file_chunk = FileChunk(
            file_id=file.id,
            workspace_id=workspace_id,
            chunk_index=idx,
            text_content=chunk.text,
            token_count=chunk.token_count,
            source_type="paperless",
        )
        db.add(file_chunk)
        await db.flush()

        # Update embedding_id with Qdrant point ID
        qdrant_id = str(file_chunk.id)
        file_chunk.embedding_id = qdrant_id

        points.append(PointStruct(
            id=qdrant_id,
            vector=vector,
            payload={
                "workspace_id": str(workspace_id),
                "file_id": str(file.id),
                "source_id": str(source_id),
                "chunk_index": idx,
                "paperless_id": doc.id,
            },
        ))

    # Batch upsert to Qdrant
    if points:
        await qdrant.upsert(
            collection_name="document_embeddings",
            points=points,
            wait=True,
        )

    logger.info(
        "paperless_doc_embedded",
        paperless_id=doc.id,
        chunks=len(chunks),
    )
    return len(chunks)


# ── Core sync function ────────────────────────────────────────────────────────


async def _sync_one_document(
    doc: PaperlessDocument,
    workspace_id: UUID,
    source_id: UUID,
    db: AsyncSession,
) -> None:
    """Sync a single Paperless document end-to-end."""
    client = get_paperless_client()

    # Fetch full content if the list response truncated it
    if not doc.content:
        doc = await client.get_document(doc.id)

    file, is_new = await _upsert_file(workspace_id, source_id, doc, db)

    if is_new:
        await _create_ingestion_state_if_new(file.id, workspace_id, db)
        # Advance from DISCOVERED → TEXT_EXTRACTED (Paperless did OCR already)
        await _advance_stages(file.id, _SKIP_TO_TEXT_EXTRACTED, db)
    # Existing file: ingestion_state may be at any stage — re-embed regardless

    chunk_count = await _embed_and_store(file, workspace_id, source_id, doc, db)

    if is_new:
        # Advance TEXT_EXTRACTED → COMPLETED
        await _advance_stages(file.id, _EMBED_TO_COMPLETED, db)

    await db.commit()
    logger.info(
        "paperless_doc_synced",
        paperless_id=doc.id,
        chunks=chunk_count,
        is_new=is_new,
    )


async def sync_all_documents(
    workspace_id: UUID,
    db: AsyncSession,
) -> dict[str, int]:
    """Incremental sync of all Paperless documents for *workspace_id*.

    Reads the cursor from the ``settings`` table, fetches documents modified
    after it, and processes each one.  Per-document errors are logged and
    skipped so a single bad document never aborts the entire run.

    Returns a summary dict with keys ``synced``, ``failed``, ``skipped``.
    """
    # Resolve workspace owner (needed for source registration)
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        logger.error("paperless_sync_workspace_not_found", workspace_id=str(workspace_id))
        return {"synced": 0, "failed": 0, "skipped": 0}

    last_sync_at = await _get_last_sync_at(workspace_id, db)
    source_id = await _get_or_create_source(workspace_id, workspace.owner_id, db)
    await db.commit()

    client = get_paperless_client()
    now = datetime.now(timezone.utc)

    synced = failed = skipped = 0

    try:
        async for doc in client.list_documents_modified_since(last_sync_at):
            if not doc.title:
                skipped += 1
                continue
            try:
                await _sync_one_document(doc, workspace_id, source_id, db)
                synced += 1
            except ServiceUnavailableError as exc:
                logger.warning(
                    "paperless_doc_sync_failed",
                    paperless_id=doc.id,
                    error_code=exc.error_code,
                )
                failed += 1
            except Exception:
                logger.warning(
                    "paperless_doc_sync_error",
                    paperless_id=doc.id,
                    exc_info=True,
                )
                failed += 1

    except ServiceUnavailableError as exc:
        logger.error("paperless_sync_unavailable", error_code=exc.error_code)
        return {"synced": synced, "failed": failed, "skipped": skipped}

    await _set_last_sync_at(workspace_id, now, db)
    await db.commit()

    logger.info(
        "paperless_sync_complete",
        workspace_id=str(workspace_id),
        synced=synced,
        failed=failed,
        skipped=skipped,
    )
    return {"synced": synced, "failed": failed, "skipped": skipped}
