# Redis Database Assignments
# ──────────────────────────
# DB 0: sessions  — JWT session cache (auth middleware)
# DB 1: queue     — Background task queue (ARQ workers)
# DB 2: paperless — Reserved for PaperlessNGX (shared instance)
# DB 3: cache     — General API cache + rate limiting

from urllib.parse import urlparse, urlunparse

import redis.asyncio as redis

from api.config import settings

REDIS_DB_SESSIONS = 0
REDIS_DB_QUEUE = 1
REDIS_DB_PAPERLESS = 2
REDIS_DB_CACHE = 3

_pools: dict[int, redis.Redis] = {}


def _base_url() -> str:
    """Strip the /db suffix from REDIS_URL to get the base connection string."""
    parsed = urlparse(settings.REDIS_URL)
    return urlunparse(parsed._replace(path=""))


def get_redis(db: int = REDIS_DB_SESSIONS) -> redis.Redis:
    """Return an async Redis client for the specified database.

    Reuses connection pools per database number.
    """
    if db not in _pools:
        _pools[db] = redis.from_url(
            f"{_base_url()}/{db}",
            decode_responses=True,
            max_connections=20,
        )
    return _pools[db]


async def ping(db: int = REDIS_DB_SESSIONS) -> bool:
    """Health check: returns True if Redis responds to PING on the given db."""
    try:
        return await get_redis(db).ping()
    except redis.RedisError:
        return False


async def close_all() -> None:
    """Close all connection pools. Call during app shutdown."""
    for client in _pools.values():
        await client.aclose()
    _pools.clear()
