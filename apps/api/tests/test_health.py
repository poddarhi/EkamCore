import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_200() -> None:
    """Health endpoint should return 200 with service status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "postgres" in data["services"]
    assert "redis" in data["services"]
    assert "qdrant" in data["services"]
