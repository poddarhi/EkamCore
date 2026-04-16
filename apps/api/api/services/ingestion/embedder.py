"""Ollama embedding generator for the ingestion pipeline (S07-002).

Wraps the Ollama /api/embed endpoint to produce 768-dimensional vectors
using nomic-embed-text.  Every embedding input is prefixed with document
metadata so the vector captures richer contextual signal for retrieval::

    File: invoice_2024.pdf | Type: application/pdf

    <chunk text here>

Error handling
──────────────
  Network / timeout  → ServiceUnavailableError("EMBEDDER_UNAVAILABLE")
  Unexpected payload → ServiceUnavailableError("EMBEDDER_BAD_RESPONSE")
  All retries fail   → last exception re-raised

Retry policy: 3 attempts, exponential backoff (0 s, 1 s, 2 s).
Concurrency: ``generate_embeddings_batch`` caps parallelism at 10 with a
semaphore to avoid saturating Ollama's single-threaded inference.

S15-007: Reuse httpx connection pool instead of creating fresh AsyncClient
per embedding call. Saves ~20ms TCP overhead per request.
"""

from __future__ import annotations

import asyncio
from typing import NamedTuple

import httpx
import structlog

from api.config import settings
from api.errors import ServiceUnavailableError

logger = structlog.get_logger()

_MODEL = "nomic-embed-text"
_EXPECTED_DIMS = 768
_TIMEOUT = httpx.Timeout(10.0, read=60.0)
_MAX_RETRIES = 3
_MAX_CONCURRENT = 10
_BACKOFF_BASE = 1.0  # seconds; attempt 0 → 0 s, 1 → 1 s, 2 → 2 s

# S15-007: Module-level connection pool for Ollama embed endpoint.
_embed_pool: httpx.AsyncClient | None = None


def _get_pool() -> httpx.AsyncClient:
    """Return the shared httpx connection pool for Ollama embeddings."""
    global _embed_pool
    if _embed_pool is None or _embed_pool.is_closed:
        _embed_pool = httpx.AsyncClient(
            timeout=_TIMEOUT,
            limits=httpx.Limits(
                max_connections=_MAX_CONCURRENT,
                max_keepalive_connections=4,
                keepalive_expiry=120.0,
            ),
        )
    return _embed_pool


async def close_pool() -> None:
    """Close the connection pool. Call during app shutdown."""
    global _embed_pool
    if _embed_pool is not None:
        await _embed_pool.aclose()
        _embed_pool = None


class EmbeddingInput(NamedTuple):
    text: str
    filename: str = ""
    mime_type: str = ""


def _build_prompt(ei: EmbeddingInput) -> str:
    """Prepend document metadata prefix per the ML/AI SKILL.md embedding rule."""
    if ei.filename or ei.mime_type:
        header = f"File: {ei.filename} | Type: {ei.mime_type}\n\n"
    else:
        header = ""
    return header + ei.text


async def _call_ollama(prompt: str) -> list[float]:
    """Single attempt: POST to /api/embed, return embedding vector."""
    url = f"{settings.OLLAMA_URL.rstrip('/')}/api/embed"
    client = _get_pool()
    try:
        resp = await client.post(url, json={"model": _MODEL, "input": prompt})
        resp.raise_for_status()
    except httpx.TimeoutException:
        raise ServiceUnavailableError(
            error_code="EMBEDDER_UNAVAILABLE",
            message="Ollama embedding request timed out.",
        )
    except httpx.RequestError:
        raise ServiceUnavailableError(
            error_code="EMBEDDER_UNAVAILABLE",
            message="Ollama is unreachable.",
        )
    except httpx.HTTPStatusError as exc:
        raise ServiceUnavailableError(
            error_code="EMBEDDER_UNAVAILABLE",
            message=f"Ollama returned HTTP {exc.response.status_code}.",
        )

    data = resp.json()
    embeddings = data.get("embeddings")
    if not embeddings or not isinstance(embeddings[0], list):
        raise ServiceUnavailableError(
            error_code="EMBEDDER_BAD_RESPONSE",
            message="Ollama /api/embed returned unexpected payload.",
        )

    vector: list[float] = embeddings[0]
    if len(vector) != _EXPECTED_DIMS:
        logger.warning(
            "embedder_unexpected_dims",
            expected=_EXPECTED_DIMS,
            got=len(vector),
        )
    return vector


# ── Retry wrapper ─────────────────────────────────────────────────────────────


async def _with_retry(prompt: str) -> list[float]:
    """Call Ollama with up to _MAX_RETRIES attempts and exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        if attempt:
            await asyncio.sleep(_BACKOFF_BASE * (attempt))  # 0 s, 1 s, 2 s
        try:
            return await _call_ollama(prompt)
        except ServiceUnavailableError as exc:
            last_exc = exc
            logger.warning(
                "embedder_retry",
                attempt=attempt + 1,
                max=_MAX_RETRIES,
                error_code=exc.error_code,
            )
    assert last_exc is not None
    raise last_exc


# ── Public API ────────────────────────────────────────────────────────────────


async def generate_embedding(
    text: str,
    filename: str = "",
    mime_type: str = "",
) -> list[float]:
    """Generate a single 768-dim embedding vector.

    Args:
        text: Chunk text to embed.
        filename: Original document filename (added to metadata prefix).
        mime_type: MIME type (added to metadata prefix).

    Returns:
        768-dimensional float list (L2-normalised by nomic-embed-text).
    """
    prompt = _build_prompt(EmbeddingInput(text=text, filename=filename, mime_type=mime_type))
    return await _with_retry(prompt)


async def generate_embeddings_batch(
    inputs: list[EmbeddingInput],
) -> list[list[float]]:
    """Generate embeddings for multiple inputs concurrently.

    Concurrency is limited to _MAX_CONCURRENT simultaneous Ollama requests
    via a semaphore.  Each call is individually retried.

    Args:
        inputs: List of :class:`EmbeddingInput` named tuples.

    Returns:
        List of 768-dim float lists, in the same order as *inputs*.
    """
    if not inputs:
        return []

    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def _bounded(ei: EmbeddingInput) -> list[float]:
        async with sem:
            return await _with_retry(_build_prompt(ei))

    return list(await asyncio.gather(*(_bounded(ei) for ei in inputs)))
