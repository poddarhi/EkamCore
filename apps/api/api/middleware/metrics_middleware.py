"""Metrics collection middleware (G-15 / ART-27).

Records request counts and latencies per endpoint group into Redis.
Aggregated to PostgreSQL hourly by metrics_flush_loop in main.py.

Privacy: records only path, method, status, latency_ms — never bodies,
query params, or PII. Fire-and-forget; never blocks the request pipeline.
"""

import time

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.services.metrics_service import record_request

logger = structlog.get_logger()


class MetricsMiddleware:
    """Pure-ASGI middleware that records request metrics to Redis."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_with_capture(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_capture)
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            path = scope.get("path", "")
            method = scope.get("method", "")

            # Fire-and-forget — never block or raise
            try:
                await record_request(
                    path=path,
                    method=method,
                    status=status_code,
                    latency_ms=latency_ms,
                )
            except Exception:
                logger.debug("metrics_middleware_record_failed", exc_info=True)
