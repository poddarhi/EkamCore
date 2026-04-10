"""Ollama LLM client for grounded QA inference (S09-001).

Wraps the Ollama /api/chat endpoint with timeouts and graceful error handling.
All network errors are converted to ServiceUnavailableError so the query router
can catch them and fall back to plain search results without a 5xx.

Models:
  SMALL_MODEL  phi3:mini    — 5 s timeout, simple queries
  LARGE_MODEL  llama3.1:8b  — 15 s timeout, complex synthesis
"""

from __future__ import annotations

import structlog
import httpx

from api.config import settings
from api.errors import ServiceUnavailableError

logger = structlog.get_logger()

SMALL_MODEL = "phi3:mini"
LARGE_MODEL = "llama3.1:8b"

# Connect timeout is kept short; read timeout matches the caller-supplied value.
_CONNECT_TIMEOUT = 5.0


async def call_llm(
    messages: list[dict[str, str]],
    model: str,
    timeout_s: float,
    temperature: float = 0.1,
) -> str:
    """POST to Ollama /api/chat (non-streaming).

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
    timeout = httpx.Timeout(_CONNECT_TIMEOUT, read=timeout_s)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                url,
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
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
