"""CSRF protection: double-submit cookie pattern."""

import secrets

from fastapi import Request, Response

from api.errors import AuthorizationError

CSRF_COOKIE_NAME = "ekamcore_csrf"
CSRF_HEADER_NAME = "x-csrf-token"


def generate_csrf_token() -> str:
    """Generate a random 32-byte hex CSRF token."""
    return secrets.token_hex(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """Set the CSRF cookie. HttpOnly=False so JavaScript can read it."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=True,
        samesite="strict",
        path="/",
    )


async def validate_csrf(request: Request) -> None:
    """FastAPI dependency: validate CSRF double-submit cookie on state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)

    if not cookie_value or not header_value:
        raise AuthorizationError(
            error_code="CSRF_VALIDATION_FAILED",
            message="CSRF token missing.",
        )

    if not secrets.compare_digest(cookie_value, header_value):
        raise AuthorizationError(
            error_code="CSRF_VALIDATION_FAILED",
            message="CSRF token mismatch.",
        )
