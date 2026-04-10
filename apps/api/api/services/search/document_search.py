"""Hybrid semantic + full-text document search (S07-003).

Pipeline:
  1. Embed the query via Ollama (P1_INTERACTIVE slot — user-facing).
  2. Search Qdrant ``document_embeddings`` with workspace_id payload filter.
  3. Search Paperless full-text API in parallel with step 1.
  4. Merge results: dedup by file_id, collapse multiple chunks to max score.
  5. Re-rank: weighted score = 0.6 × semantic + 0.4 × fulltext.
  6. Enrich with File rows from PostgreSQL (workspace-isolated).
  7. Return list[FileCard] sorted by final score.

Graceful degradation
────────────────────
Every I/O helper returns [] / None on failure — never raises.  A search
request with Qdrant down still returns Paperless results, and vice-versa.
Both failing returns an empty list (not an error).

Feature gate
────────────
``"embeddings_enabled"`` must be in ``_ENABLED_FLAGS`` — if absent the
function returns [] immediately.  This ensures the endpoint degrades
gracefully during Phase 1 rollbacks without a 5xx.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from qdrant_client.models import FieldCondition, Filter, MatchValue, ScoredPoint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File
from api.db.models.file_chunk import FileChunk
from api.errors import ServiceUnavailableError
from api.middleware.feature_gate import _ENABLED_FLAGS
from api.schemas.envelope import FileCard
from api.services.ingestion.embedder import generate_embedding
from api.services.paperless.client import get_paperless_client
from api.services.paperless.models import PaperlessDocument
from api.services.qdrant_client import get_qdrant
from api.services.resource_controller import Priority, acquire_slot

logger = structlog.get_logger()

_COLLECTION = "document_embeddings"
_SEMANTIC_WEIGHT = 0.6
_FULLTEXT_WEIGHT = 0.4
_QDRANT_LIMIT = 20     # top-K chunks fetched from Qdrant before dedup
_PAPERLESS_PAGE_SIZE = 20


# ── Internal hit model ────────────────────────────────────────────────────────


@dataclass
class _FileHit:
    file_id: UUID
    semantic_score: float = 0.0
    fulltext_score: float = 0.0
    paperless_id: int | None = None
    best_chunk_index: int = 0

    @property
    def final_score(self) -> float:
        return self.semantic_score * _SEMANTIC_WEIGHT + self.fulltext_score * _FULLTEXT_WEIGHT


# ── I/O helpers (all graceful — never raise) ──────────────────────────────────


async def _embed_query(query: str) -> list[float] | None:
    """Embed *query* under a P1_INTERACTIVE slot.  Returns None on any error."""
    try:
        async with acquire_slot(Priority.P1_INTERACTIVE):
            return await generate_embedding(query)
    except ServiceUnavailableError:
        logger.warning("document_search_embed_failed")
        return None
    except Exception:
        logger.warning("document_search_embed_failed", exc_info=True)
        return None


async def _semantic_search(
    vector: list[float],
    workspace_id: UUID,
    limit: int = _QDRANT_LIMIT,
) -> list[ScoredPoint]:
    """Search Qdrant with workspace_id payload filter.  Returns [] on any error."""
    try:
        hits = await get_qdrant().search(
            collection_name=_COLLECTION,
            query_vector=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="workspace_id",
                        match=MatchValue(value=str(workspace_id)),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )
        return hits
    except Exception:
        logger.warning("document_search_qdrant_failed", exc_info=True)
        return []


async def _fulltext_search(query: str) -> list[PaperlessDocument]:
    """Search Paperless full-text.  Returns [] on any error."""
    try:
        result = await get_paperless_client().search_documents(
            query, page=1, page_size=_PAPERLESS_PAGE_SIZE
        )
        return result.results
    except ServiceUnavailableError:
        logger.warning("document_search_paperless_failed")
        return []
    except Exception:
        logger.warning("document_search_paperless_failed", exc_info=True)
        return []


async def _enrich_from_db(
    file_ids: set[UUID],
    workspace_id: UUID,
    db: AsyncSession,
) -> dict[UUID, File]:
    """Batch-load File rows, enforcing workspace isolation and soft-delete filter."""
    if not file_ids:
        return {}
    stmt = select(File).where(
        File.id.in_(file_ids),
        File.workspace_id == workspace_id,
        File.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return {f.id: f for f in result.scalars().all()}


async def _build_paperless_id_map(
    workspace_id: UUID,
    db: AsyncSession,
) -> dict[int, UUID]:
    """Return {paperless_id: file.id} for all Paperless-sourced files in the workspace."""
    stmt = select(File).where(
        File.workspace_id == workspace_id,
        File.deleted_at.is_(None),
        File.metadata_json.is_not(None),
    )
    result = await db.execute(stmt)
    mapping: dict[int, UUID] = {}
    for f in result.scalars().all():
        if f.metadata_json and "paperless_id" in f.metadata_json:
            try:
                mapping[int(f.metadata_json["paperless_id"])] = f.id
            except (TypeError, ValueError):
                pass
    return mapping


# ── Merge & score ────────────────────────────────────────────────────────────


def _fulltext_score_for_doc(doc: PaperlessDocument, query: str) -> float:
    """Score a Paperless full-text result relative to the query.

    0.8 → query appears in document title (strongest signal)
    0.6 → appears only in content / Paperless ranked it but title doesn't match
    """
    if query.lower() in (doc.title or "").lower():
        return 0.8
    return 0.6


def _merge_results(
    qdrant_hits: list[ScoredPoint],
    paperless_docs: list[PaperlessDocument],
    paperless_id_to_file_id: dict[int, UUID],
    query: str,
) -> dict[UUID, _FileHit]:
    """Merge Qdrant + Paperless results, dedup by file_id.

    Qdrant: multiple chunks from the same file collapse to one hit, keeping
    the maximum semantic score and the chunk_index of that best hit.

    Paperless: each doc is mapped to a local file_id via
    *paperless_id_to_file_id*.  Docs without a local file row are skipped
    (they haven't been synced yet).
    """
    hits: dict[UUID, _FileHit] = {}

    # ── Qdrant leg ────────────────────────────────────────────────────────────
    for point in qdrant_hits:
        payload = point.payload or {}
        raw_fid = payload.get("file_id")
        if not raw_fid:
            continue
        try:
            file_id = UUID(str(raw_fid))
        except (ValueError, AttributeError):
            continue

        score = float(point.score)
        chunk_idx = int(payload.get("chunk_index", 0))
        paperless_id = payload.get("paperless_id")

        if file_id not in hits:
            hits[file_id] = _FileHit(
                file_id=file_id,
                semantic_score=score,
                best_chunk_index=chunk_idx,
                paperless_id=paperless_id,
            )
        else:
            existing = hits[file_id]
            if score > existing.semantic_score:
                existing.semantic_score = score
                existing.best_chunk_index = chunk_idx

    # ── Paperless leg ─────────────────────────────────────────────────────────
    for doc in paperless_docs:
        file_id = paperless_id_to_file_id.get(doc.id)
        if file_id is None:
            continue  # not yet synced locally

        ft_score = _fulltext_score_for_doc(doc, query)
        if file_id not in hits:
            hits[file_id] = _FileHit(
                file_id=file_id,
                fulltext_score=ft_score,
                paperless_id=doc.id,
            )
        else:
            hits[file_id].fulltext_score = ft_score
            if hits[file_id].paperless_id is None:
                hits[file_id].paperless_id = doc.id

    return hits


def _build_file_card(hit: _FileHit, file: File) -> FileCard:
    meta = file.metadata_json or {}
    return FileCard(
        id=file.id,
        priority_score=round(hit.final_score, 4),
        source_ids=[file.source_id] if file.source_id else [],
        payload={
            "filename": file.filename,
            "mime_type": file.mime_type,
            "path": file.path,
            "paperless_id": meta.get("paperless_id"),
            "correspondent_id": meta.get("correspondent_id"),
            "tag_ids": meta.get("tag_ids", []),
            "best_chunk_index": hit.best_chunk_index,
            "semantic_score": round(hit.semantic_score, 4),
            "fulltext_score": round(hit.fulltext_score, 4),
        },
    )


# ── Public API ────────────────────────────────────────────────────────────────


async def search_documents(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[FileCard]:
    """Hybrid semantic + full-text document search.

    Returns an empty list (never raises) when embeddings are disabled or
    when both I/O legs fail.
    """
    if "embeddings_enabled" not in _ENABLED_FLAGS:
        logger.warning("document_search_flag_disabled")
        return []

    # Phase 1: embed query + Paperless full-text — run concurrently
    vector, paperless_docs = await asyncio.gather(
        _embed_query(query),
        _fulltext_search(query),
    )

    # Phase 2: Qdrant (needs embedding result from phase 1)
    qdrant_hits: list[ScoredPoint] = []
    if vector is not None:
        qdrant_hits = await _semantic_search(vector, workspace_id, limit=_QDRANT_LIMIT)

    if not qdrant_hits and not paperless_docs:
        return []

    # Build paperless_id → file_id lookup (workspace-scoped DB query)
    paperless_id_to_file_id = await _build_paperless_id_map(workspace_id, db)

    # Merge and score
    hits = _merge_results(qdrant_hits, paperless_docs, paperless_id_to_file_id, query)
    if not hits:
        return []

    # Enrich with File rows (workspace-isolated)
    file_rows = await _enrich_from_db(set(hits.keys()), workspace_id, db)

    # Build cards: skip hits without a local File row, sort, paginate
    cards: list[FileCard] = []
    for file_id, hit in hits.items():
        file = file_rows.get(file_id)
        if file is None:
            continue  # workspace isolation: file not in this workspace
        cards.append(_build_file_card(hit, file))

    cards.sort(key=lambda c: c.priority_score, reverse=True)
    return cards[offset: offset + limit]


async def count_documents(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
) -> int:
    """Approximate document count: distinct file_ids with embeddings in this workspace.

    Uses a fast COUNT query rather than running the full hybrid pipeline.
    This matches the pattern of count_calendar / count_reminders / count_contacts.
    """
    if "embeddings_enabled" not in _ENABLED_FLAGS:
        return 0
    stmt = (
        select(func.count(func.distinct(FileChunk.file_id)))
        .where(FileChunk.workspace_id == workspace_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one() or 0
