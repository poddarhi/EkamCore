from typing import Any

import httpx
import structlog
from fastapi import APIRouter
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


def _check_face_model() -> dict[str, Any]:
    """Check InsightFace singleton state (S11-005).

    Reads `FaceModel.instance().loaded` + any recorded load error.
    Never triggers a load — status is observational only. Safe to call
    before the model has ever been touched.

    Treated as OPTIONAL (same as Ollama/Paperless): face_model failure
    does NOT flip the overall /health status to "degraded".
    """
    try:
        from api.services.face.face_model import face_model_status

        snap = face_model_status()
        return {
            "status": "healthy" if snap.get("loaded") else "unhealthy",
            "loaded": snap.get("loaded"),
            "load_error": snap.get("load_error"),
            "detector_version": snap.get("detector_version"),
            "recognizer_version": snap.get("recognizer_version"),
        }
    except Exception as e:
        # Module-level import failure (pyproject deps not installed) is
        # surfaced as unhealthy but never raises.
        logger.warning("face_model_health_failed", error_type=type(e).__name__)
        return {
            "status": "unhealthy",
            "loaded": False,
            "load_error": f"{type(e).__name__}: {e}",
        }


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint that verifies connectivity to all backend services."""
    postgres = await _check_postgres()
    redis = await _check_redis()
    qdrant = await _check_qdrant()
    paperless = await _check_paperless()
    ollama = await _check_ollama()
    face_model = _check_face_model()

    services = {
        "postgres": postgres,
        "redis": redis,
        "qdrant": qdrant,
        "paperless": paperless,
        "ollama": ollama,
        "face_model": face_model,
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
