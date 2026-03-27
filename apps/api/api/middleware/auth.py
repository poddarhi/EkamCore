"""Authentication dependency for FastAPI route handlers."""

from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.schemas.auth import CurrentUser
from api.services.auth import decode_access_token
from api.errors import AuthenticationError

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Extract and validate JWT from Authorization header. Returns CurrentUser."""
    if credentials is None:
        raise AuthenticationError(error_code="AUTH_TOKEN_MISSING", message="Authorization header required.")

    claims = decode_access_token(credentials.credentials)

    return CurrentUser(
        id=UUID(claims["sub"]),
        role=claims["role"],
        workspace_ids=[UUID(ws) for ws in claims.get("workspaces", [])],
        session_id=UUID(claims["jti"]),
    )
