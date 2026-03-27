from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.db.session import get_db
from api.main import app
from api.services.auth import hash_password

TEST_DATABASE_URL = "postgresql+asyncpg://ekamcore:ekamcore_dev_password@localhost:5432/ekamcore"


@pytest_asyncio.fixture(scope="session")
async def test_session_factory():
    """Session-scoped engine and session factory, created on the test event loop."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await eng.dispose()


@pytest_asyncio.fixture
async def db(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_session_factory) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def seed_user(test_session_factory) -> dict:
    """Create a test user with workspace and return credentials."""
    email = f"test-{uuid4().hex[:8]}@ekamcore.dev"
    password = "testpassword123"

    async with test_session_factory() as db:
        user = User(
            email=email,
            display_name="Test User",
            password_hash=hash_password(password),
            role="standard",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        workspace = Workspace(name="Test Workspace", type="personal", owner_id=user.id)
        db.add(workspace)
        await db.flush()

        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin")
        db.add(member)
        await db.commit()

        return {
            "user_id": user.id,
            "email": email,
            "password": password,
            "workspace_id": workspace.id,
        }


@pytest_asyncio.fixture
async def auth_tokens(client: AsyncClient, seed_user: dict) -> dict:
    """Login and return tokens + cookies."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seed_user["email"], "password": seed_user["password"]},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    cookies = response.cookies
    return {
        "access_token": data["access_token"],
        "refresh_cookie": cookies.get("ekamcore_refresh"),
        "csrf_token": cookies.get("ekamcore_csrf"),
        **seed_user,
    }


@pytest.fixture(autouse=True)
def mock_rate_limiter_redis():
    """Auto-mock the rate_limiter Redis client so tests don't need a running Redis.

    Individual tests (e.g. test_bruteforce.py) can override this by patching
    get_redis themselves with specific return values.
    """
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)  # no failures by default
    mock.delete = AsyncMock()
    pipe = Mock()
    pipe.incr = Mock(return_value=pipe)
    pipe.expire = Mock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, True])
    mock.pipeline = Mock(return_value=pipe)

    with patch("api.services.rate_limiter.get_redis", return_value=mock):
        yield mock
