from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Request
from redis.asyncio import Redis
from sqlalchemy import text

from api.config import settings

logger = structlog.get_logger()
router = APIRouter()


async def _check_postgres() -> dict[str, Any]:
    """Check PostgreSQL connectivity."""
    try:
        from api.db.session import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as e:
        logger.warning("postgres_health_failed", error_type=type(e).__name__)
        return {"status": "unhealthy", "error": type(e).__name__}


async def _check_redis() -> dict[str, Any]:
    """Check Redis connectivity."""
    try:
        client = Redis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.aclose()
        return {"status": "healthy"}
    except Exception as e:
        logger.warning("redis_health_failed", error_type=type(e).__name__)
        return {"status": "unhealthy", "error": type(e).__name__}


async def _check_qdrant() -> dict[str, Any]:
    """Check Qdrant connectivity."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.QDRANT_URL}/healthz", timeout=5.0)
            if resp.status_code == 200:
                return {"status": "healthy"}
            return {"status": "unhealthy", "error": f"status_{resp.status_code}"}
    except Exception as e:
        logger.warning("qdrant_health_failed", error_type=type(e).__name__)
        return {"status": "unhealthy", "error": type(e).__name__}


async def _check_paperless() -> dict[str, Any]:
    """Check PaperlessNGX via the typed API client (validates token too)."""
    try:
        from api.services.paperless.client import get_paperless_client
        ok = await get_paperless_client().health_check()
        return {"status": "healthy" if ok else "unhealthy"}
    except Exception as e:
        logger.warning("paperless_health_failed", error_type=type(e).__name__)
        return {"status": "unhealthy", "error": type(e).__name__}


async def _check_ollama() -> dict[str, Any]:
    """Check Ollama (native on host via host.docker.internal)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://host.docker.internal:11434/api/tags", timeout=5.0)
            if resp.status_code == 200:
                return {"status": "healthy"}
            return {"status": "unhealthy", "error": f"status_{resp.status_code}"}
    except Exception as e:
        logger.warning("ollama_health_failed", error_type=type(e).__name__)
        return {"status": "unhealthy", "error": type(e).__name__}


async def _check_face_pipeline() -> dict[str, Any]:
    """Check face pipeline observability surface (S11-005, extended in S11-008).

    Returns the InsightFace singleton state PLUS four pipeline-level
    aggregates:
      - consent_active_workspaces: count of workspaces with active consent
      - active_backfills: count of face_backfill_jobs in 'running' state
      - last_detection_at: most recent face_detections.created_at across
        all workspaces, or null if none yet

    Treated as OPTIONAL (same as Ollama/Paperless): face pipeline failure
    does NOT flip the overall /health status to "degraded". Aggregate
    counts are system-wide (no per-workspace filtering in /health) —
    PII-safe because counts are not personally identifying.
    """
    base: dict[str, Any] = {
        "status": "unhealthy",
        # S11-005 shipped `loaded`; S11-008 adds `model_loaded` as a
        # more-specific alias. Both are kept so existing consumers
        # (tests, the StoragePage tile, external monitors) don't break.
        "loaded": False,
        "model_loaded": False,
        "load_error": None,
        "detector_version": None,
        "recognizer_version": None,
        "consent_active_workspaces": 0,
        "active_backfills": 0,
        "last_detection_at": None,
    }

    # ── Singleton model state ──
    try:
        from api.services.face.face_model import face_model_status

        snap = face_model_status()
        loaded = bool(snap.get("loaded"))
        base["loaded"] = loaded
        base["model_loaded"] = loaded
        base["load_error"] = snap.get("load_error")
        base["detector_version"] = snap.get("detector_version")
        base["recognizer_version"] = snap.get("recognizer_version")
        base["status"] = "healthy" if loaded else "unhealthy"
    except Exception as e:
        logger.warning("face_model_health_failed", error_type=type(e).__name__)
        base["load_error"] = f"{type(e).__name__}: {e}"

    # ── Aggregate pipeline state (best-effort) ──
    try:
        from sqlalchemy import func, select

        from api.db.models.face_backfill_job import FaceBackfillJob
        from api.db.models.face_detection import FaceDetection
        from api.db.models.setting import Setting
        from api.db.session import async_session

        async with async_session() as db:
            # Count workspaces where consent is accepted and not revoked.
            # The consent record lives in settings.value_json as a JSONB
            # blob — this is the same shape written by ConsentService.
            consent_count_result = await db.execute(
                select(func.count()).select_from(Setting).where(
                    Setting.namespace == "privacy",
                    Setting.key == "face_clustering_consent",
                    Setting.value_json["accepted"].astext == "true",
                    Setting.value_json["revoked_at"].astext.is_(None),
                )
            )
            base["consent_active_workspaces"] = int(
                consent_count_result.scalar() or 0
            )

            active_jobs_result = await db.execute(
                select(func.count()).select_from(FaceBackfillJob).where(
                    FaceBackfillJob.state == "running"
                )
            )
            base["active_backfills"] = int(active_jobs_result.scalar() or 0)

            last_detection_result = await db.execute(
                select(func.max(FaceDetection.created_at)).where(
                    FaceDetection.deleted_at.is_(None)
                )
            )
            last_at = last_detection_result.scalar()
            base["last_detection_at"] = (
                last_at.isoformat() if last_at is not None else None
            )
    except Exception as e:
        # Health endpoint must never hard-fail — log, surface empty values.
        logger.warning(
            "face_pipeline_health_aggregate_failed", error_type=type(e).__name__
        )

    return base


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Health check endpoint that verifies connectivity to all backend services."""
    postgres = await _check_postgres()
    redis = await _check_redis()
    qdrant = await _check_qdrant()
    paperless = await _check_paperless()
    ollama = await _check_ollama()
    face_pipeline = await _check_face_pipeline()

    services = {
        "postgres": postgres,
        "redis": redis,
        "qdrant": qdrant,
        "paperless": paperless,
        "ollama": ollama,
        # Backwards-compat: S11-005 shipped "face_model" — the extended
        # S11-008 block is a strict superset so older clients still see
        # `loaded`/`detector_version` under the same key.
        "face_model": face_pipeline,
    }

    # S14-005: pack scheduler status.
    pack_scheduler = getattr(request.app.state, "pack_scheduler", None)
    if pack_scheduler is not None:
        services["pack_scheduler"] = pack_scheduler.health()
    else:
        services["pack_scheduler"] = {
            "running": False,
            "jobs_registered": 0,
            "next_daily_run": None,
            "next_weekly_run": None,
            "last_run": None,
        }

    # Core services: postgres, redis, qdrant. Paperless, Ollama, and
    # face_model are optional — their failure does NOT degrade overall
    # status.
    core_healthy = all(
        services[s]["status"] == "healthy" for s in ("postgres", "redis", "qdrant")
    )

    return {
        "status": "healthy" if core_healthy else "degraded",
        "services": services,
        "version": "0.1.0",
        "ram_mode": "production-lean",
        "note": "Ollama runs natively on host (not in Docker) for direct Apple Silicon GPU access",
    }
