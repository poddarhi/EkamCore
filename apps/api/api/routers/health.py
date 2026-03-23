from typing import Any

import httpx
import structlog
from fastapi import APIRouter
from redis.asyncio import Redis

from api.config import settings

logger = structlog.get_logger()
router = APIRouter()


async def _check_postgres() -> dict[str, Any]:
    """Check PostgreSQL connectivity."""
    try:
        from sqlalchemy import text

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


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint that verifies connectivity to all backend services."""
    postgres = await _check_postgres()
    redis = await _check_redis()
    qdrant = await _check_qdrant()

    services = {
        "postgres": postgres,
        "redis": redis,
        "qdrant": qdrant,
    }

    all_healthy = all(s["status"] == "healthy" for s in services.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": services,
    }
