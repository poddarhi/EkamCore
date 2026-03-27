import time

import structlog
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger()


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

        async def send_with_timing(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_timing)
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            correlation_id = scope.get("state", {}).get("correlation_id", "unknown")

            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status=status_code,
                latency_ms=latency_ms,
                correlation_id=correlation_id,
            )
