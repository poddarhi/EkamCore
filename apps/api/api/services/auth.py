"""Authentication service: login, refresh, logout, token creation."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import argon2
import structlog
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db.models.session import Session
from api.db.models.user import User
from api.db.models.workspace_member import WorkspaceMember
from api.errors import AuthenticationError

logger = structlog.get_logger()

_ph = argon2.PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

REFRESH_COOKIE_NAME = "ekamcore_refresh"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except argon2.exceptions.VerifyMismatchError:
        return False


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_access_token(user_id: UUID, role: str, workspace_ids: list[UUID], session_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "role": role,
        "workspaces": [str(ws_id) for ws_id in workspace_ids],
        "jti": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "iss": "ekamcore",
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], issuer="ekamcore")
    except JWTError as e:
        error_str = str(e).lower()
        if "expired" in error_str:
            raise AuthenticationError(error_code="AUTH_TOKEN_EXPIRED", message="Access token has expired.")
        raise AuthenticationError(error_code="AUTH_TOKEN_INVALID", message="Invalid access token.")


async def _get_workspace_ids(user_id: UUID, db: AsyncSession) -> list[UUID]:
    result = await db.execute(
        select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id)
    )
    return list(result.scalars().all())


async def login(email: str, password: str, db: AsyncSession, device_info: dict | None = None) -> tuple[str, str, int]:
    """Authenticate user, create session, return (access_token, refresh_token, expires_in)."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        logger.warning("auth_login_failed", email_provided=bool(email))
        raise AuthenticationError(error_code="AUTH_INVALID_CREDENTIALS", message="Incorrect email or password.")

    if not user.is_active:
        logger.warning("auth_login_inactive", user_id=str(user.id))
        raise AuthenticationError(error_code="AUTH_INVALID_CREDENTIALS", message="Incorrect email or password.")

    workspace_ids = await _get_workspace_ids(user.id, db)

    refresh_token = secrets.token_urlsafe(32)
    refresh_hash = _hash_refresh_token(refresh_token)

    session = Session(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        device_info=device_info,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        is_revoked=False,
    )
    db.add(session)
    await db.flush()

    access_token = _create_access_token(user.id, user.role, workspace_ids, session.id)
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    logger.info("auth_login_success", user_id=str(user.id))
    return access_token, refresh_token, expires_in


async def refresh(refresh_token: str, db: AsyncSession) -> tuple[str, str, int]:
    """Rotate refresh token. Returns (access_token, new_refresh_token, expires_in)."""
    token_hash = _hash_refresh_token(refresh_token)

    result = await db.execute(
        select(Session).where(Session.refresh_token_hash == token_hash)
    )
    session = result.scalar_one_or_none()

    if session is None:
        # Possible replay: check if this hash was used on a now-revoked session
        # We can't find it because it was already rotated. This IS a replay.
        logger.warning("auth_refresh_replay_suspected")
        raise AuthenticationError(error_code="AUTH_REFRESH_INVALID", message="Invalid refresh token.")

    if session.is_revoked:
        # Replay detected — revoke ALL sessions for this user
        logger.warning("auth_refresh_replay_detected", user_id=str(session.user_id), session_id=str(session.id))
        await db.execute(
            update(Session).where(Session.user_id == session.user_id).values(is_revoked=True)
        )
        await db.commit()
        raise AuthenticationError(error_code="AUTH_REFRESH_REVOKED", message="Session has been revoked. Please login again.")

    now = datetime.now(timezone.utc)
    if session.expires_at < now:
        logger.warning("auth_refresh_expired", session_id=str(session.id))
        raise AuthenticationError(error_code="AUTH_REFRESH_EXPIRED", message="Refresh token has expired.")

    # Rotate: mark old hash as revoked, issue new token
    session.is_revoked = True
    session.last_used_at = now

    # Create new session for the new refresh token
    new_refresh_token = secrets.token_urlsafe(32)
    new_hash = _hash_refresh_token(new_refresh_token)

    new_session = Session(
        user_id=session.user_id,
        refresh_token_hash=new_hash,
        device_info=session.device_info,
        expires_at=session.expires_at,
        is_revoked=False,
    )
    db.add(new_session)
    await db.flush()

    workspace_ids = await _get_workspace_ids(session.user_id, db)
    user_result = await db.execute(select(User).where(User.id == session.user_id))
    user = user_result.scalar_one()

    access_token = _create_access_token(user.id, user.role, workspace_ids, new_session.id)
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    logger.info("auth_refresh_success", user_id=str(user.id))
    return access_token, new_refresh_token, expires_in


async def logout(session_id: UUID, db: AsyncSession) -> None:
    """Revoke the session identified by the JWT jti claim."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if session and not session.is_revoked:
        session.is_revoked = True
        logger.info("auth_logout_success", user_id=str(session.user_id), session_id=str(session_id))
    else:
        logger.info("auth_logout_already_revoked", session_id=str(session_id))
