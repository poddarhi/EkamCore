from qdrant_client import AsyncQdrantClient

from api.config import settings

_client: AsyncQdrantClient | None = None


def get_qdrant() -> AsyncQdrantClient:
    """Return a singleton async Qdrant client."""
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=10.0,
            check_compatibility=False,
        )
    return _client


async def ping() -> bool:
    """Health check: returns True if Qdrant is reachable."""
    try:
        await get_qdrant().get_collections()
        return True
    except Exception:
        return False


async def close() -> None:
    """Close the client. Call during app shutdown."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
