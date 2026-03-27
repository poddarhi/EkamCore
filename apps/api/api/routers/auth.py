import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthenticationError
from api.middleware.auth import get_current_user
from api.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from api.services.auth import REFRESH_COOKIE_NAME, login, logout, refresh

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login_endpoint(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    device_info = {"user_agent": request.headers.get("user-agent", "")}
    client_ip = request.client.host if request.client else "unknown"

    access_token, refresh_token, expires_in = await login(
        email=body.email,
        password=body.password,
        db=db,
        device_info=device_info,
        ip=client_ip,
    )

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600,
        path="/api/v1/auth",
    )

    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/refresh")
async def refresh_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise AuthenticationError(error_code="AUTH_REFRESH_MISSING", message="Refresh token cookie not found.")

    access_token, new_refresh_token, expires_in = await refresh(
        refresh_token=refresh_token,
        db=db,
    )

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600,
        path="/api/v1/auth",
    )

    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", status_code=204)
async def logout_endpoint(
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await logout(session_id=user.session_id, db=db)
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/v1/auth")
