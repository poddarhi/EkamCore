"""Ollama LLM client for grounded QA inference (S09-001).

Wraps the Ollama /api/chat endpoint with timeouts and graceful error handling.
All network errors are converted to ServiceUnavailableError so the query router
can catch them and fall back to plain search results without a 5xx.

Models:
  SMALL_MODEL  phi3:mini    — 5 s timeout, simple queries
  LARGE_MODEL  llama3.1:8b  — 15 s timeout, complex synthesis

Resource management:
  Every inference call acquires a P1_INTERACTIVE slot from the resource
  controller so background work (embeddings, sync) is preempted while the
  user is waiting for an answer.

S15-007: Reuse httpx connection pool instead of creating a new AsyncClient
per inference call. Saves TCP+TLS handshake overhead (~20-50ms per call).
"""

from __future__ import annotations

import structlog
import httpx

from api.config import settings
from api.errors import ServiceUnavailableError
from api.services.resource_controller import Priority, acquire_slot

logger = structlog.get_logger()

SMALL_MODEL = "phi3:mini"
LARGE_MODEL = "llama3.1:8b"

# Connect timeout is kept short; read timeout matches the caller-supplied value.
_CONNECT_TIMEOUT = 5.0

# S15-007: Module-level connection pool — reused across all inference calls.
# Limits keep-alive connections to Ollama's single endpoint.
_llm_pool: httpx.AsyncClient | None = None


def _get_pool() -> httpx.AsyncClient:
    """Return the shared httpx connection pool for Ollama inference."""
    global _llm_pool
    if _llm_pool is None or _llm_pool.is_closed:
        _llm_pool = httpx.AsyncClient(
            timeout=httpx.Timeout(_CONNECT_TIMEOUT, read=30.0),
            limits=httpx.Limits(
                max_connections=4,
                max_keepalive_connections=2,
                keepalive_expiry=120.0,
            ),
        )
    return _llm_pool


async def close_pool() -> None:
    """Close the connection pool. Call during app shutdown."""
    global _llm_pool
    if _llm_pool is not None:
        await _llm_pool.aclose()
        _llm_pool = None


async def call_llm(
    messages: list[dict[str, str]],
    model: str,
    timeout_s: float,
    temperature: float = 0.1,
) -> str:
    """POST to Ollama /api/chat (non-streaming) with P1 slot management.

    Acquires a P1_INTERACTIVE resource slot before calling Ollama so
    background work is preempted while the user waits for a response.

    Args:
        messages: Chat message list, e.g. [{"role": "system", ...}, {"role": "user", ...}].
        model:    Ollama model name (e.g. "phi3:mini").
        timeout_s: Read timeout in seconds.
        temperature: Sampling temperature (0.0–1.0).

    Returns:
        The ``message.content`` string from the Ollama response.

    Raises:
        ServiceUnavailableError: On timeout, connection error, or bad HTTP status.
    """
    url = f"{settings.OLLAMA_URL.rstrip('/')}/api/chat"
    client = _get_pool()

    async with acquire_slot(Priority.P1_INTERACTIVE):
        try:
            resp = await client.post(
                url,
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=httpx.Timeout(_CONNECT_TIMEOUT, read=timeout_s),
            )
            resp.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("llm_client_timeout", model=model, timeout_s=timeout_s)
            raise ServiceUnavailableError(
                error_code="LLM_TIMEOUT",
                message=f"LLM inference timed out after {timeout_s}s.",
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "llm_client_http_error",
                model=model,
                status=exc.response.status_code,
            )
            raise ServiceUnavailableError(
                error_code="LLM_ERROR",
                message=f"Ollama returned HTTP {exc.response.status_code}.",
            )
        except httpx.RequestError:
            logger.warning("llm_client_request_error", model=model)
            raise ServiceUnavailableError(
                error_code="LLM_UNAVAILABLE",
                message="Ollama is unreachable.",
            )

    data = resp.json()
    content: str = (data.get("message") or {}).get("content", "")
    if not content:
        raise ServiceUnavailableError(
            error_code="LLM_EMPTY_RESPONSE",
            message="Ollama returned an empty response.",
        )
    return content
