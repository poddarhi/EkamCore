import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

import structlog
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from api.errors import EkamCoreError
from api.logging_config import configure_logging
from api.middleware.correlation import CorrelationIdMiddleware
from api.middleware.error_handler import ekamcore_error_handler, unhandled_error_handler
from api.middleware.feature_gate import _ENABLED_FLAGS
from api.middleware.logging import LoggingMiddleware
from api.middleware.metrics_middleware import MetricsMiddleware
from api.routers import admin, auth, face_consent, health, internal, metrics, notifications, photos, query, recap, reminders, search, settings, sources, today

configure_logging()
logger = structlog.get_logger()

_PAPERLESS_SYNC_INTERVAL = 15 * 60  # 15 minutes


async def _paperless_sync_loop() -> None:
    """Background task: sync Paperless documents every 15 minutes per workspace."""
    from api.db.session import async_session
    from api.db.models.workspace import Workspace
    from api.services.paperless.sync import sync_all_documents

    await asyncio.sleep(30)  # brief startup delay to let DB connections settle
    while True:
        if "embeddings_enabled" in _ENABLED_FLAGS:
            try:
                async with async_session() as db:
                    result = await db.execute(select(Workspace))
                    workspaces = result.scalars().all()

                for workspace in workspaces:
                    try:
                        async with async_session() as db:
                            summary = await sync_all_documents(workspace_id=workspace.id, db=db)
                            logger.info(
                                "paperless_scheduled_sync_complete",
                                workspace_id=str(workspace.id),
                                **summary,
                            )
                    except Exception:
                        logger.warning(
                            "paperless_scheduled_sync_error",
                            workspace_id=str(workspace.id),
                            exc_info=True,
                        )
            except Exception:
                logger.warning("paperless_sync_loop_error", exc_info=True)

        await asyncio.sleep(_PAPERLESS_SYNC_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    logger.info("ekamcore_api_starting")

    # Phase 3 safety check: if the face pipeline could ever be activated
    # but FACE_EMBED_KEY is missing, log CRITICAL. The face_pipeline_active()
    # gate will return False for all workspaces, so no crash occurs — this
    # is observability only.
    from api.config import settings as _app_settings

    if not _app_settings.FACE_EMBED_KEY:
        logger.critical(
            "face_embed_key_missing",
            message=(
                "FACE_EMBED_KEY env var is not set. The face clustering "
                "pipeline will remain disabled for all workspaces, even "
                "if face_clustering_enabled is activated and consent is "
                "granted. Generate a key with: python -c 'from "
                "cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'"
            ),
        )

    try:
        from api.services.qdrant_init import init_collections

        await init_collections()
        logger.info("qdrant_collections_initialized")
    except Exception:
        logger.warning("qdrant_init_failed", exc_info=True)

    sync_task = asyncio.create_task(_paperless_sync_loop())
    logger.info("paperless_sync_scheduler_started")

    # Metrics flusher (G-15): Redis aggregates → PostgreSQL every hour
    from api.services.metrics_service import metrics_flush_loop

    metrics_task = asyncio.create_task(metrics_flush_loop())
    logger.info("metrics_flush_scheduler_started")

    yield

    sync_task.cancel()
    metrics_task.cancel()
    for task in (sync_task, metrics_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

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
    app.add_middleware(MetricsMiddleware)
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
    app.include_router(sources.router)
    app.include_router(internal.router)
    app.include_router(admin.router)
    app.include_router(today.router)
    app.include_router(recap.router)
    app.include_router(query.router)
    app.include_router(search.router)
    app.include_router(reminders.router)
    app.include_router(photos.router)
    app.include_router(settings.router)
    app.include_router(notifications.router)
    app.include_router(metrics.router)
    app.include_router(face_consent.router)

    return app


app = create_app()
