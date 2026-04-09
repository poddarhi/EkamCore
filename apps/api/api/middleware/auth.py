"""Authentication dependency for FastAPI route handlers."""

from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.errors import AuthenticationError
from api.schemas.auth import CurrentUser
from api.services.auth import decode_access_token
from api.services.redis_client import REDIS_DB_SESSIONS, get_redis

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Extract and validate JWT from Authorization header. Returns CurrentUser.

    Checks the Redis revocation blocklist so that tokens from logged-out sessions
    are rejected immediately, within their 15-minute JWT window.
    """
    if credentials is None:
        raise AuthenticationError(error_code="AUTH_TOKEN_MISSING", message="Authorization header required.")

    claims = decode_access_token(credentials.credentials)

    # Blocklist check: logout writes revoked:{jti} to Redis db0
    jti = claims.get("jti", "")
    r = get_redis(REDIS_DB_SESSIONS)
    if await r.get(f"revoked:{jti}"):
        raise AuthenticationError(
            error_code="AUTH_SESSION_REVOKED",
            message="Session has been revoked. Please login again.",
        )

    return CurrentUser(
        id=UUID(claims["sub"]),
        role=claims["role"],
        workspace_ids=[UUID(ws) for ws in claims.get("workspaces", [])],
        session_id=UUID(claims["jti"]),
    )
