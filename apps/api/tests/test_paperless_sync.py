"""Tests for the Paperless document sync worker (S07-002).

Mocks: PaperlessClient, async DB session, Qdrant client, embedder, chunker.
No network or database required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from api.services.paperless.models import PaperlessDocument
from api.services.paperless.sync import (
    _content_hash,
    _infer_mime,
    sync_all_documents,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_doc(
    doc_id: int = 1,
    title: str = "Test Doc",
    content: str = "Some document content for testing purposes.",
    original_file_name: str = "test.pdf",
) -> PaperlessDocument:
    return PaperlessDocument(
        id=doc_id,
        title=title,
        content=content,
        correspondent=None,
        document_type=None,
        tags=[],
        created=datetime(2024, 1, 1, tzinfo=timezone.utc),
        modified=datetime(2024, 4, 1, tzinfo=timezone.utc),
        added=datetime(2024, 1, 2, tzinfo=timezone.utc),
        archive_serial_number=None,
        original_file_name=original_file_name,
    )


def _uuid() -> UUID:
    return UUID(str(uuid.uuid4()))


# ── Unit helpers ──────────────────────────────────────────────────────────────


def test_content_hash_is_sha256_hex():
    h = _content_hash("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_content_hash_is_deterministic():
    assert _content_hash("same text") == _content_hash("same text")


def test_content_hash_differs_for_different_text():
    assert _content_hash("text A") != _content_hash("text B")


def test_infer_mime_pdf():
    assert _infer_mime("document.pdf") == "application/pdf"


def test_infer_mime_txt():
    assert _infer_mime("notes.txt") == "text/plain"


def test_infer_mime_unknown_extension():
    assert _infer_mime("file.ekam") == "application/octet-stream"


def test_infer_mime_none_filename():
    assert _infer_mime(None) == "application/octet-stream"


def test_infer_mime_empty_filename():
    assert _infer_mime("") == "application/octet-stream"


# ── sync_all_documents ────────────────────────────────────────────────────────


async def _async_gen(*items):
    for item in items:
        yield item


@pytest.fixture
def workspace_id() -> UUID:
    return _uuid()


@pytest.fixture
def mock_workspace(workspace_id):
    ws = MagicMock()
    ws.id = workspace_id
    ws.owner_id = _uuid()
    return ws


def _build_db_mock(workspace):
    """Build a mock AsyncSession that fakes the DB interactions."""
    db = AsyncMock()

    # db.get(Workspace, ...) → workspace
    db.get = AsyncMock(return_value=workspace)

    # All SELECT statements return empty (no existing settings/sources/files/states)
    empty_result = MagicMock()
    empty_result.scalar_one_or_none = MagicMock(return_value=None)
    empty_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    db.execute = AsyncMock(return_value=empty_result)

    # add / flush / commit / delete are no-ops
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()

    return db


@pytest.mark.asyncio
async def test_sync_all_documents_workspace_not_found():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    workspace_id = _uuid()

    result = await sync_all_documents(workspace_id=workspace_id, db=db)

    assert result == {"synced": 0, "failed": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_sync_all_documents_skips_untitled_docs(mock_workspace, workspace_id):
    db = _build_db_mock(mock_workspace)

    untitled_doc = _make_doc(doc_id=1, title="")
    titled_doc = _make_doc(doc_id=2, title="Valid Title")

    async def _fake_gen(*args, **kwargs):
        for doc in [untitled_doc, titled_doc]:
            yield doc

    with (
        patch("api.services.paperless.sync.get_paperless_client") as mock_client_fn,
        patch("api.services.paperless.sync.advance_stage", new_callable=AsyncMock),
        patch("api.services.paperless.sync.chunk_text", return_value=[]),
        patch("api.services.paperless.sync.get_qdrant"),
    ):
        mock_client = MagicMock()
        mock_client.list_documents_modified_since = _fake_gen
        mock_client_fn.return_value = mock_client

        result = await sync_all_documents(workspace_id=workspace_id, db=db)

    assert result["skipped"] == 1


@pytest.mark.asyncio
async def test_sync_all_documents_counts_synced(mock_workspace, workspace_id):
    db = _build_db_mock(mock_workspace)
    doc = _make_doc()

    async def _fake_gen(*args, **kwargs):
        yield doc

    # Fake a file object with an id attribute
    fake_file = MagicMock()
    fake_file.id = _uuid()
    # is_new path: execute returns None for existing file lookup (new file)
    empty_result = MagicMock()
    empty_result.scalar_one_or_none = MagicMock(return_value=None)
    empty_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    db.execute = AsyncMock(return_value=empty_result)
    db.flush = AsyncMock(side_effect=lambda: setattr(fake_file, "id", _uuid()))
    db.add = MagicMock()

    with (
        patch("api.services.paperless.sync.get_paperless_client") as mock_client_fn,
        patch("api.services.paperless.sync._upsert_file", new_callable=AsyncMock,
              return_value=(fake_file, True)),
        patch("api.services.paperless.sync._create_ingestion_state_if_new", new_callable=AsyncMock,
              return_value=True),
        patch("api.services.paperless.sync._advance_stages", new_callable=AsyncMock),
        patch("api.services.paperless.sync._embed_and_store", new_callable=AsyncMock,
              return_value=3),
    ):
        mock_client = MagicMock()
        mock_client.list_documents_modified_since = _fake_gen
        mock_client_fn.return_value = mock_client

        result = await sync_all_documents(workspace_id=workspace_id, db=db)

    assert result["synced"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_sync_all_documents_isolates_per_doc_errors(mock_workspace, workspace_id):
    db = _build_db_mock(mock_workspace)

    doc1 = _make_doc(doc_id=1)
    doc2 = _make_doc(doc_id=2)

    async def _fake_gen(*args, **kwargs):
        yield doc1
        yield doc2

    call_count = 0

    async def _failing_upsert(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated DB error on doc 1")
        fake_file = MagicMock()
        fake_file.id = _uuid()
        return fake_file, True

    with (
        patch("api.services.paperless.sync.get_paperless_client") as mock_client_fn,
        patch("api.services.paperless.sync._upsert_file", side_effect=_failing_upsert),
        patch("api.services.paperless.sync._create_ingestion_state_if_new", new_callable=AsyncMock,
              return_value=True),
        patch("api.services.paperless.sync._advance_stages", new_callable=AsyncMock),
        patch("api.services.paperless.sync._embed_and_store", new_callable=AsyncMock,
              return_value=2),
    ):
        mock_client = MagicMock()
        mock_client.list_documents_modified_since = _fake_gen
        mock_client_fn.return_value = mock_client

        result = await sync_all_documents(workspace_id=workspace_id, db=db)

    assert result["failed"] == 1
    assert result["synced"] == 1


@pytest.mark.asyncio
async def test_sync_all_documents_no_docs_updates_cursor(mock_workspace, workspace_id):
    db = _build_db_mock(mock_workspace)

    async def _empty_gen(*args, **kwargs):
        return
        yield  # make this an async generator

    with patch("api.services.paperless.sync.get_paperless_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.list_documents_modified_since = _empty_gen
        mock_client_fn.return_value = mock_client

        result = await sync_all_documents(workspace_id=workspace_id, db=db)

    # Should have committed at least once (cursor update)
    assert db.commit.await_count >= 1
    assert result == {"synced": 0, "failed": 0, "skipped": 0}


# ── _embed_and_store integration ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_and_store_empty_content_returns_zero():
    from api.services.paperless.sync import _embed_and_store

    fake_file = MagicMock()
    fake_file.id = _uuid()
    doc = _make_doc(content="")
    workspace_id = _uuid()
    source_id = _uuid()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    ))
    db.flush = AsyncMock()

    result = await _embed_and_store(fake_file, workspace_id, source_id, doc, db)
    assert result == 0


@pytest.mark.asyncio
async def test_embed_and_store_calls_qdrant_upsert():
    from api.services.ingestion.chunker import Chunk
    from api.services.paperless.sync import _embed_and_store

    fake_file = MagicMock()
    fake_file.id = _uuid()
    doc = _make_doc(content="Long enough content that actually produces chunks.")
    workspace_id = _uuid()
    source_id = _uuid()

    fake_chunk = Chunk(text="some text", token_count=3, start_char=0, end_char=9)

    fake_file_chunk = MagicMock()
    fake_file_chunk.id = _uuid()
    fake_file_chunk.embedding_id = None

    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    mock_qdrant = AsyncMock()

    with (
        patch("api.services.paperless.sync._delete_old_chunks", new_callable=AsyncMock),
        patch("api.services.paperless.sync.chunk_text", return_value=[fake_chunk]),
        patch("api.services.paperless.sync.generate_embedding", new_callable=AsyncMock,
              return_value=[0.1] * 768),
        patch("api.services.paperless.sync.acquire_slot") as mock_slot,
        patch("api.services.paperless.sync.get_qdrant", return_value=mock_qdrant),
        patch("api.services.paperless.sync.FileChunk", return_value=fake_file_chunk),
    ):
        # make acquire_slot work as an async context manager
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        count = await _embed_and_store(fake_file, workspace_id, source_id, doc, db)

    assert count == 1
    mock_qdrant.upsert.assert_awaited_once()
    call_kwargs = mock_qdrant.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "document_embeddings"
    assert len(call_kwargs["points"]) == 1
    assert call_kwargs["wait"] is True
