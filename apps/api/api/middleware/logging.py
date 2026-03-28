"""Structured request logging middleware (pure ASGI).

Logs every request with: correlation_id, method, path, status, latency_ms, user_id.
NEVER logs: request/response body, query params with user data, passwords, tokens, emails, PII.
"""

import time
import traceback

import structlog
from jose import jwt
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.config import settings

logger = structlog.get_logger()


def _extract_user_id(scope: Scope) -> str | None:
    """Extract user_id from the Authorization Bearer JWT, if present."""
    headers = dict(scope.get("headers", []))
    auth_value = headers.get(b"authorization", b"").decode()
    if not auth_value.startswith("Bearer "):
        return None
    token = auth_value[7:]
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        return payload.get("sub")
    except Exception:
        return None


class LoggingMiddleware:
    """Structured request logging. Never logs PII (pure ASGI)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        start = time.perf_counter()
        status_code = 500
        exc_text: str | None = None

        async def send_with_timing(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_timing)
        except Exception as exc:
            exc_text = traceback.format_exc()
            raise
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            correlation_id = scope.get("state", {}).get("correlation_id", "unknown")
            user_id = _extract_user_id(scope)

            log_kwargs: dict = {
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "latency_ms": latency_ms,
                "correlation_id": correlation_id,
            }
            if user_id:
                log_kwargs["user_id"] = user_id

            if status_code >= 500:
                if exc_text:
                    log_kwargs["stack_trace"] = exc_text
                logger.error("request_completed", **log_kwargs)
            elif status_code >= 400:
                logger.warning("request_completed", **log_kwargs)
            else:
                logger.info("request_completed", **log_kwargs)
