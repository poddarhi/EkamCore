"""Tests for the Ollama embedding generator (S07-002).

All HTTP calls are intercepted — no network required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.errors import ServiceUnavailableError
from api.services.ingestion.embedder import (
    EmbeddingInput,
    _build_prompt,
    generate_embedding,
    generate_embeddings_batch,
)


# ── _build_prompt ────────────────────────────────────────────────────────────


def test_build_prompt_with_filename_and_mime():
    ei = EmbeddingInput(text="chunk text", filename="doc.pdf", mime_type="application/pdf")
    prompt = _build_prompt(ei)
    assert prompt.startswith("File: doc.pdf | Type: application/pdf\n\n")
    assert prompt.endswith("chunk text")


def test_build_prompt_without_metadata():
    ei = EmbeddingInput(text="bare text")
    assert _build_prompt(ei) == "bare text"


def test_build_prompt_only_filename():
    ei = EmbeddingInput(text="text", filename="notes.txt")
    prompt = _build_prompt(ei)
    assert "File: notes.txt" in prompt


# ── generate_embedding ───────────────────────────────────────────────────────


def _fake_768_vector() -> list[float]:
    return [0.1] * 768


def _mock_ollama_response(vector: list[float] | None = None) -> MagicMock:
    """Build a mock httpx.Response for the Ollama /api/embed endpoint."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={"embeddings": [vector or _fake_768_vector()]})
    return resp


@pytest.mark.asyncio
async def test_generate_embedding_returns_vector():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_mock_ollama_response())

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        result = await generate_embedding("hello world")

    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)


@pytest.mark.asyncio
async def test_generate_embedding_posts_correct_model():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_mock_ollama_response())

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        await generate_embedding("text", filename="file.pdf", mime_type="application/pdf")

    call_kwargs = mock_client.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert body["model"] == "nomic-embed-text"
    assert "File: file.pdf | Type: application/pdf" in body["input"]


@pytest.mark.asyncio
async def test_generate_embedding_timeout_raises_service_unavailable():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ServiceUnavailableError) as exc_info:
            await generate_embedding("text")
    assert exc_info.value.error_code == "EMBEDDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_generate_embedding_connect_error_raises_service_unavailable():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ServiceUnavailableError) as exc_info:
            await generate_embedding("text")
    assert exc_info.value.error_code == "EMBEDDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_generate_embedding_http_error_raises_service_unavailable():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    error_response = MagicMock(status_code=500)
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=error_response
        )
    )

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ServiceUnavailableError) as exc_info:
            await generate_embedding("text")
    assert exc_info.value.error_code == "EMBEDDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_generate_embedding_bad_response_raises_error():
    """Response missing 'embeddings' key raises EMBEDDER_BAD_RESPONSE."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.raise_for_status = MagicMock(return_value=None)
    bad_resp.json = MagicMock(return_value={"error": "model not found"})
    mock_client.post = AsyncMock(return_value=bad_resp)

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ServiceUnavailableError) as exc_info:
            await generate_embedding("text")
    assert exc_info.value.error_code == "EMBEDDER_BAD_RESPONSE"


# ── Retry behaviour ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_embedding_retries_on_failure_then_succeeds():
    """First 2 attempts fail; 3rd succeeds — should return the vector."""
    call_count = 0

    async def _post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("timeout")
        return _mock_ollama_response()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _post

    with (
        patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client),
        patch("api.services.ingestion.embedder.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await generate_embedding("text")

    assert len(result) == 768
    assert call_count == 3


@pytest.mark.asyncio
async def test_generate_embedding_raises_after_all_retries_fail():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with (
        patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client),
        patch("api.services.ingestion.embedder.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(ServiceUnavailableError) as exc_info:
            await generate_embedding("text")
    assert exc_info.value.error_code == "EMBEDDER_UNAVAILABLE"


# ── generate_embeddings_batch ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_embeddings_batch_empty():
    result = await generate_embeddings_batch([])
    assert result == []


@pytest.mark.asyncio
async def test_generate_embeddings_batch_preserves_order():
    inputs = [
        EmbeddingInput(text="chunk A"),
        EmbeddingInput(text="chunk B"),
        EmbeddingInput(text="chunk C"),
    ]

    call_order = []

    async def _post(url, *, json, **kwargs):
        call_order.append(json["input"])
        # Return distinct vectors: [0.1]*768 for A, [0.2]*768 for B, etc.
        idx = len(call_order) - 1
        return _mock_ollama_response([float(idx + 1) / 10] * 768)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _post

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        results = await generate_embeddings_batch(inputs)

    assert len(results) == 3
    assert all(isinstance(v, list) for v in results)


@pytest.mark.asyncio
async def test_generate_embeddings_batch_returns_one_vector_per_input():
    inputs = [EmbeddingInput(text=f"text {i}") for i in range(5)]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_mock_ollama_response())

    with patch("api.services.ingestion.embedder.httpx.AsyncClient", return_value=mock_client):
        results = await generate_embeddings_batch(inputs)

    assert len(results) == 5
