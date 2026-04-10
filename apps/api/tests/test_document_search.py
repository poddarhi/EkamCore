"""Tests for the hybrid semantic+fulltext document search (S07-003).

All I/O is mocked — no network, database, Qdrant, or Ollama required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from api.errors import ServiceUnavailableError
from api.schemas.envelope import FileCard
from api.services.paperless.models import PaperlessDocument
from api.services.search.document_search import (
    _FileHit,
    _build_file_card,
    _embed_query,
    _enrich_from_db,
    _fulltext_search,
    _fulltext_score_for_doc,
    _merge_results,
    _semantic_search,
    count_documents,
    search_documents,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _uuid() -> UUID:
    return UUID(str(uuid.uuid4()))


def _make_doc(
    doc_id: int = 1,
    title: str = "Test Invoice",
    content: str = "Some document content",
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
        original_file_name="test.pdf",
    )


def _make_scored_point(file_id: UUID, score: float, chunk_index: int = 0,
                        paperless_id: int = 1) -> MagicMock:
    point = MagicMock()
    point.score = score
    point.payload = {
        "file_id": str(file_id),
        "chunk_index": chunk_index,
        "paperless_id": paperless_id,
        "workspace_id": "irrelevant",
    }
    return point


def _make_file(file_id: UUID | None = None, workspace_id: UUID | None = None) -> MagicMock:
    f = MagicMock()
    f.id = file_id or _uuid()
    f.workspace_id = workspace_id or _uuid()
    f.source_id = _uuid()
    f.filename = "invoice.pdf"
    f.mime_type = "application/pdf"
    f.path = f"paperless://documents/1"
    f.metadata_json = {"paperless_id": 1, "correspondent_id": None, "tag_ids": []}
    f.deleted_at = None
    return f


# ── _embed_query ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_query_returns_vector_on_success():
    with (
        patch("api.services.search.document_search.acquire_slot") as mock_slot,
        patch("api.services.search.document_search.generate_embedding",
              new_callable=AsyncMock, return_value=[0.1] * 768),
    ):
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _embed_query("test query")

    assert result is not None
    assert len(result) == 768


@pytest.mark.asyncio
async def test_embed_query_returns_none_on_service_unavailable():
    with (
        patch("api.services.search.document_search.acquire_slot") as mock_slot,
        patch("api.services.search.document_search.generate_embedding",
              new_callable=AsyncMock,
              side_effect=ServiceUnavailableError(error_code="EMBEDDER_UNAVAILABLE",
                                                   message="down")),
    ):
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _embed_query("test query")

    assert result is None


@pytest.mark.asyncio
async def test_embed_query_returns_none_on_generic_exception():
    with (
        patch("api.services.search.document_search.acquire_slot") as mock_slot,
        patch("api.services.search.document_search.generate_embedding",
              new_callable=AsyncMock, side_effect=RuntimeError("unexpected")),
    ):
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _embed_query("test query")

    assert result is None


# ── _semantic_search ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_semantic_search_passes_workspace_filter():
    workspace_id = _uuid()
    mock_qdrant = AsyncMock()
    mock_qdrant.search = AsyncMock(return_value=[])

    with patch("api.services.search.document_search.get_qdrant", return_value=mock_qdrant):
        await _semantic_search([0.1] * 768, workspace_id)

    call_kwargs = mock_qdrant.search.call_args.kwargs
    assert call_kwargs["collection_name"] == "document_embeddings"
    assert call_kwargs["with_payload"] is True
    filter_obj = call_kwargs["query_filter"]
    assert filter_obj.must[0].key == "workspace_id"
    assert filter_obj.must[0].match.value == str(workspace_id)


@pytest.mark.asyncio
async def test_semantic_search_returns_points_on_success():
    workspace_id = _uuid()
    file_id = _uuid()
    mock_point = _make_scored_point(file_id, score=0.9)
    mock_qdrant = AsyncMock()
    mock_qdrant.search = AsyncMock(return_value=[mock_point])

    with patch("api.services.search.document_search.get_qdrant", return_value=mock_qdrant):
        result = await _semantic_search([0.1] * 768, workspace_id)

    assert result == [mock_point]


@pytest.mark.asyncio
async def test_semantic_search_returns_empty_on_qdrant_error():
    workspace_id = _uuid()
    mock_qdrant = AsyncMock()
    mock_qdrant.search = AsyncMock(side_effect=Exception("connection refused"))

    with patch("api.services.search.document_search.get_qdrant", return_value=mock_qdrant):
        result = await _semantic_search([0.1] * 768, workspace_id)

    assert result == []


# ── _fulltext_search ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fulltext_search_returns_docs_on_success():
    doc = _make_doc()
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.results = [doc]
    mock_client.search_documents = AsyncMock(return_value=mock_result)

    with patch("api.services.search.document_search.get_paperless_client",
               return_value=mock_client):
        result = await _fulltext_search("invoice")

    assert result == [doc]


@pytest.mark.asyncio
async def test_fulltext_search_returns_empty_on_service_unavailable():
    mock_client = MagicMock()
    mock_client.search_documents = AsyncMock(
        side_effect=ServiceUnavailableError(error_code="PAPERLESS_UNAVAILABLE", message="down")
    )

    with patch("api.services.search.document_search.get_paperless_client",
               return_value=mock_client):
        result = await _fulltext_search("invoice")

    assert result == []


@pytest.mark.asyncio
async def test_fulltext_search_returns_empty_on_generic_exception():
    mock_client = MagicMock()
    mock_client.search_documents = AsyncMock(side_effect=ConnectionError("refused"))

    with patch("api.services.search.document_search.get_paperless_client",
               return_value=mock_client):
        result = await _fulltext_search("invoice")

    assert result == []


# ── _fulltext_score_for_doc ───────────────────────────────────────────────────


def test_fulltext_score_title_match():
    doc = _make_doc(title="Invoice 2024")
    assert _fulltext_score_for_doc(doc, "invoice") == 0.8


def test_fulltext_score_title_match_case_insensitive():
    doc = _make_doc(title="INVOICE 2024")
    assert _fulltext_score_for_doc(doc, "invoice") == 0.8


def test_fulltext_score_content_only():
    doc = _make_doc(title="Random Document", content="This mentions invoice")
    assert _fulltext_score_for_doc(doc, "invoice") == 0.6


def test_fulltext_score_no_match():
    doc = _make_doc(title="Other Document", content="Other content")
    # Even if no match, Paperless returned it — use content-match score
    assert _fulltext_score_for_doc(doc, "invoice") == 0.6


# ── _merge_results ────────────────────────────────────────────────────────────


def test_merge_results_dedup_by_file_id():
    file_id = _uuid()
    points = [
        _make_scored_point(file_id, score=0.9, chunk_index=0),
        _make_scored_point(file_id, score=0.7, chunk_index=1),
    ]
    result = _merge_results(points, [], {}, "query")
    assert len(result) == 1
    assert result[file_id].semantic_score == 0.9
    assert result[file_id].best_chunk_index == 0


def test_merge_results_takes_max_semantic_score():
    file_id = _uuid()
    points = [
        _make_scored_point(file_id, score=0.6, chunk_index=1),
        _make_scored_point(file_id, score=0.95, chunk_index=3),
        _make_scored_point(file_id, score=0.8, chunk_index=2),
    ]
    result = _merge_results(points, [], {}, "query")
    assert result[file_id].semantic_score == 0.95
    assert result[file_id].best_chunk_index == 3


def test_merge_results_fulltext_title_match():
    file_id = _uuid()
    doc = _make_doc(doc_id=42, title="Invoice 2024")
    paperless_map = {42: file_id}
    result = _merge_results([], [doc], paperless_map, "invoice")
    assert file_id in result
    assert result[file_id].fulltext_score == 0.8


def test_merge_results_fulltext_content_match():
    file_id = _uuid()
    doc = _make_doc(doc_id=5, title="Random Title")
    paperless_map = {5: file_id}
    result = _merge_results([], [doc], paperless_map, "invoice")
    assert result[file_id].fulltext_score == 0.6


def test_merge_results_both_legs():
    file_id = _uuid()
    doc_id = 1
    points = [_make_scored_point(file_id, score=0.85, chunk_index=0, paperless_id=doc_id)]
    doc = _make_doc(doc_id=doc_id, title="Invoice 2024")
    paperless_map = {doc_id: file_id}
    result = _merge_results(points, [doc], paperless_map, "invoice")
    hit = result[file_id]
    assert hit.semantic_score == 0.85
    assert hit.fulltext_score == 0.8
    expected = round(0.85 * 0.6 + 0.8 * 0.4, 4)
    assert round(hit.final_score, 4) == expected


def test_merge_results_skips_paperless_docs_without_local_file():
    doc = _make_doc(doc_id=999, title="Not synced yet")
    result = _merge_results([], [doc], {}, "test")
    assert len(result) == 0


def test_merge_results_semantic_only_leg():
    file_id = _uuid()
    points = [_make_scored_point(file_id, score=0.75)]
    result = _merge_results(points, [], {}, "query")
    hit = result[file_id]
    assert hit.semantic_score == 0.75
    assert hit.fulltext_score == 0.0
    assert round(hit.final_score, 4) == round(0.75 * 0.6, 4)


def test_merge_results_skips_point_without_file_id():
    bad_point = MagicMock()
    bad_point.score = 0.9
    bad_point.payload = {"chunk_index": 0}  # no file_id
    result = _merge_results([bad_point], [], {}, "query")
    assert len(result) == 0


# ── _build_file_card ──────────────────────────────────────────────────────────


def test_build_file_card_shape():
    file_id = _uuid()
    file = _make_file(file_id=file_id)
    hit = _FileHit(file_id=file_id, semantic_score=0.8, fulltext_score=0.7,
                   paperless_id=1, best_chunk_index=2)
    card = _build_file_card(hit, file)
    assert isinstance(card, FileCard)
    assert card.id == file_id
    assert card.priority_score == round(0.8 * 0.6 + 0.7 * 0.4, 4)
    assert card.payload["best_chunk_index"] == 2
    assert card.payload["semantic_score"] == 0.8
    assert card.payload["fulltext_score"] == 0.7


# ── search_documents ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_documents_returns_empty_when_flag_disabled():
    with patch("api.services.search.document_search._ENABLED_FLAGS", set()):
        result = await search_documents("query", _uuid(), AsyncMock())
    assert result == []


@pytest.mark.asyncio
async def test_search_documents_returns_empty_when_both_legs_fail():
    workspace_id = _uuid()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    ))

    with (
        patch("api.services.search.document_search._ENABLED_FLAGS", {"embeddings_enabled"}),
        patch("api.services.search.document_search._embed_query",
              new_callable=AsyncMock, return_value=None),
        patch("api.services.search.document_search._fulltext_search",
              new_callable=AsyncMock, return_value=[]),
    ):
        result = await search_documents("query", workspace_id, db)

    assert result == []


@pytest.mark.asyncio
async def test_search_documents_graceful_on_qdrant_failure():
    """Paperless leg still works when Qdrant/embedding fails."""
    workspace_id = _uuid()
    file_id = _uuid()
    doc = _make_doc(doc_id=1, title="Invoice")
    file = _make_file(file_id=file_id)
    file.metadata_json = {"paperless_id": 1, "tag_ids": [], "correspondent_id": None}

    db = AsyncMock()
    # _build_paperless_id_map query
    paperless_files_result = MagicMock()
    paperless_files_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[file]))
    )
    # _enrich_from_db query
    enrich_result = MagicMock()
    enrich_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[file]))
    )
    db.execute = AsyncMock(side_effect=[paperless_files_result, enrich_result])

    with (
        patch("api.services.search.document_search._ENABLED_FLAGS", {"embeddings_enabled"}),
        patch("api.services.search.document_search._embed_query",
              new_callable=AsyncMock, return_value=None),  # embedding fails
        patch("api.services.search.document_search._fulltext_search",
              new_callable=AsyncMock, return_value=[doc]),
    ):
        result = await search_documents("invoice", workspace_id, db)

    assert len(result) == 1
    assert isinstance(result[0], FileCard)


@pytest.mark.asyncio
async def test_search_documents_returns_file_cards():
    workspace_id = _uuid()
    file_id = _uuid()
    doc_id = 42
    file = _make_file(file_id=file_id)
    file.metadata_json = {"paperless_id": doc_id, "tag_ids": [], "correspondent_id": None}

    mock_point = _make_scored_point(file_id, score=0.9, paperless_id=doc_id)

    db = AsyncMock()
    paperless_files_result = MagicMock()
    paperless_files_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[file]))
    )
    enrich_result = MagicMock()
    enrich_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[file]))
    )
    db.execute = AsyncMock(side_effect=[paperless_files_result, enrich_result])

    with (
        patch("api.services.search.document_search._ENABLED_FLAGS", {"embeddings_enabled"}),
        patch("api.services.search.document_search._embed_query",
              new_callable=AsyncMock, return_value=[0.1] * 768),
        patch("api.services.search.document_search._fulltext_search",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.search.document_search._semantic_search",
              new_callable=AsyncMock, return_value=[mock_point]),
    ):
        result = await search_documents("invoice", workspace_id, db)

    assert len(result) == 1
    assert result[0].type == "file"
    assert result[0].id == file_id


@pytest.mark.asyncio
async def test_search_documents_pagination():
    """offset and limit are applied after scoring."""
    workspace_id = _uuid()
    file_ids = [_uuid() for _ in range(5)]
    files = [_make_file(file_id=fid) for fid in file_ids]
    for i, f in enumerate(files):
        f.metadata_json = {"paperless_id": i + 1, "tag_ids": [], "correspondent_id": None}

    points = [_make_scored_point(fid, score=1.0 - i * 0.1, paperless_id=i + 1)
              for i, fid in enumerate(file_ids)]

    db = AsyncMock()
    paperless_result = MagicMock()
    paperless_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=files))
    )
    enrich_result = MagicMock()
    enrich_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=files))
    )
    db.execute = AsyncMock(side_effect=[paperless_result, enrich_result])

    with (
        patch("api.services.search.document_search._ENABLED_FLAGS", {"embeddings_enabled"}),
        patch("api.services.search.document_search._embed_query",
              new_callable=AsyncMock, return_value=[0.1] * 768),
        patch("api.services.search.document_search._fulltext_search",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.search.document_search._semantic_search",
              new_callable=AsyncMock, return_value=points),
    ):
        result = await search_documents("invoice", workspace_id, db, limit=2, offset=1)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_search_documents_workspace_isolation():
    """File in Qdrant results but belonging to different workspace is excluded."""
    workspace_id = _uuid()
    other_workspace_id = _uuid()
    file_id = _uuid()

    # The file exists but belongs to a different workspace
    file_wrong_ws = _make_file(file_id=file_id, workspace_id=other_workspace_id)
    file_wrong_ws.metadata_json = {"paperless_id": 1, "tag_ids": [], "correspondent_id": None}

    mock_point = _make_scored_point(file_id, score=0.9)

    db = AsyncMock()
    # _build_paperless_id_map returns empty (file not in this workspace)
    empty_result = MagicMock()
    empty_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    db.execute = AsyncMock(side_effect=[empty_result, empty_result])

    with (
        patch("api.services.search.document_search._ENABLED_FLAGS", {"embeddings_enabled"}),
        patch("api.services.search.document_search._embed_query",
              new_callable=AsyncMock, return_value=[0.1] * 768),
        patch("api.services.search.document_search._fulltext_search",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.search.document_search._semantic_search",
              new_callable=AsyncMock, return_value=[mock_point]),
    ):
        result = await search_documents("invoice", workspace_id, db)

    # Qdrant returned the point but workspace isolation removes it
    assert result == []


# ── count_documents ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count_documents_returns_zero_when_flag_disabled():
    with patch("api.services.search.document_search._ENABLED_FLAGS", set()):
        result = await count_documents("query", _uuid(), AsyncMock())
    assert result == 0


@pytest.mark.asyncio
async def test_count_documents_returns_count_from_db():
    db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=7)
    db.execute = AsyncMock(return_value=count_result)

    with patch("api.services.search.document_search._ENABLED_FLAGS", {"embeddings_enabled"}):
        result = await count_documents("query", _uuid(), db)

    assert result == 7


# ── search_all integration ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_all_includes_file_type_by_default():
    """search_all with no types arg includes 'file' in results."""
    from api.services.query.search import search_all

    workspace_id = _uuid()
    file_id = _uuid()
    file_card = FileCard(
        id=file_id,
        priority_score=0.85,
        source_ids=[],
        payload={"filename": "test.pdf"},
    )

    db = AsyncMock()

    with (
        patch("api.services.query.search.search_calendar",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.query.search.count_calendar",
              new_callable=AsyncMock, return_value=0),
        patch("api.services.query.search.search_reminders",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.query.search.count_reminders",
              new_callable=AsyncMock, return_value=0),
        patch("api.services.query.search.search_contacts",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.query.search.count_contacts",
              new_callable=AsyncMock, return_value=0),
        patch("api.services.query.search.search_files",
              new_callable=AsyncMock, return_value=[file_card]),
        patch("api.services.query.search.count_files",
              new_callable=AsyncMock, return_value=1),
        patch("api.services.query.search.search_photos",
              new_callable=AsyncMock, return_value=([], 0)),
    ):
        cards, facets = await search_all("invoice", workspace_id, db)

    assert any(c.id == file_id for c in cards)
    assert facets["file"] == 1


@pytest.mark.asyncio
async def test_search_all_file_type_filter():
    """types=['file'] calls only search_files, not search_calendar."""
    from api.services.query.search import search_all

    workspace_id = _uuid()
    db = AsyncMock()

    mock_search_calendar = AsyncMock(return_value=[])
    mock_search_files = AsyncMock(return_value=[])
    mock_count_files = AsyncMock(return_value=0)

    with (
        patch("api.services.query.search.search_calendar", mock_search_calendar),
        patch("api.services.query.search.search_files", mock_search_files),
        patch("api.services.query.search.count_files", mock_count_files),
    ):
        await search_all("invoice", workspace_id, db, types=["file"])

    mock_search_calendar.assert_not_awaited()
    mock_search_files.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_all_cross_type_sort_by_score():
    """FileCard with score 0.9 ranks above EventCard with score 0.7."""
    from api.schemas.envelope import EventCard
    from api.services.query.search import search_all

    workspace_id = _uuid()
    db = AsyncMock()

    event_card = EventCard(id=_uuid(), priority_score=0.7, payload={"title": "Meeting"})
    file_card = FileCard(id=_uuid(), priority_score=0.9, payload={"filename": "invoice.pdf"})

    with (
        patch("api.services.query.search.search_calendar",
              new_callable=AsyncMock, return_value=[event_card]),
        patch("api.services.query.search.count_calendar",
              new_callable=AsyncMock, return_value=1),
        patch("api.services.query.search.search_reminders",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.query.search.count_reminders",
              new_callable=AsyncMock, return_value=0),
        patch("api.services.query.search.search_contacts",
              new_callable=AsyncMock, return_value=[]),
        patch("api.services.query.search.count_contacts",
              new_callable=AsyncMock, return_value=0),
        patch("api.services.query.search.search_files",
              new_callable=AsyncMock, return_value=[file_card]),
        patch("api.services.query.search.count_files",
              new_callable=AsyncMock, return_value=1),
        patch("api.services.query.search.search_photos",
              new_callable=AsyncMock, return_value=([], 0)),
    ):
        cards, _ = await search_all("invoice", workspace_id, db)

    assert cards[0].type == "file"
    assert cards[1].type == "event"
