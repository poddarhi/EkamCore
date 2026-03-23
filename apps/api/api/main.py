from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import EkamCoreError
from api.middleware.correlation import CorrelationIdMiddleware
from api.middleware.error_handler import ekamcore_error_handler, unhandled_error_handler
from api.middleware.logging import LoggingMiddleware
from api.routers import health

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    logger.info("ekamcore_api_starting")
    yield
    logger.info("ekamcore_api_shutting_down")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="EkamCore API",
        description="Private, local-first life assistant API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware (order matters: last added = first executed)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://localhost", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(EkamCoreError, ekamcore_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)  # type: ignore[arg-type]

    # Routers
    app.include_router(health.router)

    return app


app = create_app()
