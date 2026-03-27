import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CorrelationIdMiddleware:
    """Adds a unique correlation ID to each request (pure ASGI)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        scope.setdefault("state", {})
        scope["state"]["correlation_id"] = correlation_id

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_correlation)
