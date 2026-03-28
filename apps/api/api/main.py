from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

import structlog
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import EkamCoreError
from api.logging_config import configure_logging
from api.middleware.correlation import CorrelationIdMiddleware
from api.middleware.error_handler import ekamcore_error_handler, unhandled_error_handler
from api.middleware.logging import LoggingMiddleware
from api.routers import auth, health

configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    logger.info("ekamcore_api_starting")
    try:
        from api.services.qdrant_init import init_collections

        await init_collections()
        logger.info("qdrant_collections_initialized")
    except Exception:
        logger.warning("qdrant_init_failed", exc_info=True)
    yield
    from api.services.qdrant_client import close as close_qdrant
    from api.services.redis_client import close_all as close_redis

    await close_qdrant()
    await close_redis()
    logger.info("ekamcore_api_shut_down")


def _load_openapi_spec() -> dict | None:
    """Load the hand-written OpenAPI spec from the repo root."""
    spec_path = Path(__file__).resolve().parents[2] / "openapi" / "ekamcore.yaml"
    if not spec_path.exists():
        # Fallback: check relative to working directory
        spec_path = Path("openapi/ekamcore.yaml")
    if spec_path.exists():
        return yaml.safe_load(spec_path.read_text())
    return None


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="EkamCore API",
        description="Private, local-first life assistant API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Serve the hand-written OpenAPI spec at /docs and /openapi.json
    spec = _load_openapi_spec()
    if spec:
        app.openapi_schema = spec

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
    app.include_router(auth.router)

    return app


app = create_app()
