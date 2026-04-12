"""Face clustering consent API endpoints (S11-003).

Three endpoints under /api/v1/settings/face-clustering/consent:

  GET    — return current consent state + current consent text (always,
           so the UI can detect copy updates)
  POST   — grant consent for the authenticated user's workspace
  DELETE — revoke consent and synchronously hard-delete all face data

All endpoints:
  - Require authentication
  - POST/DELETE require CSRF (double-submit cookie)
  - Rate limited: 10 actions/minute/user (Redis)
  - Workspace member (not admin) — the user grants/revokes for their own
    workspace

The workspace is taken from the authenticated user's first workspace_id
(users typically have exactly one). No workspace_id query parameter is
exposed on these endpoints because consent is inherently per-workspace
and tampering with that parameter would be a confused deputy risk.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import (
    AuthorizationError,
    ConflictError,
    RateLimitError,
)
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.schemas.auth import CurrentUser
from api.services.face import consent_service
from api.services.face.consent_text import (
    CURRENT_CONSENT_TEXT,
    CURRENT_CONSENT_VERSION,
)
from api.services.face.hard_delete import DeleteReport
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/settings/face-clustering/consent",
    tags=["face-consent"],
)


# ── Rate limiting: 10/min/user ─────────────────────────────────────────────

_RATE_LIMIT_KEY_PREFIX = "rl:face_consent:"
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW_SECS = 60


async def _check_rate_limit(user_id: str) -> None:
    """Enforce 10 consent actions per minute per user."""
    r = get_redis(REDIS_DB_CACHE)
    key = f"{_RATE_LIMIT_KEY_PREFIX}{user_id}"

    count_str = await r.get(key)
    if count_str is not None and int(count_str) >= _RATE_LIMIT_MAX:
        ttl = await r.ttl(key)
        raise RateLimitError(
            error_code="RATE_LIMIT_EXCEEDED",
            message=f"Too many consent changes. Try again in {max(ttl, 1)} seconds.",
            details={"retry_after_seconds": max(ttl, 1)},
        )

    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, _RATE_LIMIT_WINDOW_SECS)
    await pipe.execute()


def _resolve_workspace(user: CurrentUser) -> UUID:
    """Return the workspace to apply this consent action against.

    Users typically have exactly one workspace in Phase 3. If the user
    has none, we refuse rather than silently no-op.
    """
    if not user.workspace_ids:
        raise AuthorizationError(
            error_code="NO_WORKSPACE",
            message="User has no workspace.",
        )
    return user.workspace_ids[0]


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Caddy terminates TLS and forwards the real
    client IP in X-Forwarded-For, so we prefer that header if present."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry in a chain is the original client
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _client_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "unknown")


# ── Response models ────────────────────────────────────────────────────────


class ConsentStateResponse(BaseModel):
    """Returned by GET /consent — full current state."""

    accepted: bool
    version: str | None = None
    granted_at: datetime | None = None
    revoked_at: datetime | None = None
    current_text_version: str
    current_text: str


class ConsentGrantRequest(BaseModel):
    accepted: bool = Field(..., description="Must be true to grant consent")
    version_acknowledged: str = Field(
        ..., description="Consent text version the user has read and accepted"
    )


class ConsentGrantResponse(BaseModel):
    accepted: bool
    version: str
    granted_at: datetime
    current_text_version: str


class DeleteReportResponse(BaseModel):
    """Response from DELETE /consent — what was erased."""

    detection_count: int
    cluster_count: int
    qdrant_point_count: int
    duration_ms: int


# ── GET: current state + text ──────────────────────────────────────────────


@router.get("", response_model=ConsentStateResponse)
async def get_consent(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentStateResponse:
    """Return the workspace's current consent state and the current
    consent text body. Always includes the text so the UI can detect
    copy updates and prompt for re-consent.

    No CSRF (safe method). No rate limit (read-only).
    """
    workspace_id = _resolve_workspace(user)
    record = await consent_service.get_active_consent(workspace_id, db)

    if record is None:
        return ConsentStateResponse(
            accepted=False,
            version=None,
            granted_at=None,
            revoked_at=None,
            current_text_version=CURRENT_CONSENT_VERSION,
            current_text=CURRENT_CONSENT_TEXT,
        )

    return ConsentStateResponse(
        accepted=True,
        version=record.version,
        granted_at=record.granted_at,
        revoked_at=None,
        current_text_version=CURRENT_CONSENT_VERSION,
        current_text=CURRENT_CONSENT_TEXT,
    )


# ── POST: grant ────────────────────────────────────────────────────────────


@router.post(
    "",
    dependencies=[Depends(validate_csrf)],
    response_model=ConsentGrantResponse,
)
async def post_consent(
    body: ConsentGrantRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentGrantResponse:
    """Grant face clustering consent for the caller's workspace.

    Requires the client to echo the exact version string from the
    current consent text. A mismatch returns 409 CONSENT_VERSION_STALE
    — the UI must refresh and re-prompt.
    """
    workspace_id = _resolve_workspace(user)
    await _check_rate_limit(str(user.id))

    if not body.accepted:
        raise ConflictError(
            error_code="CONSENT_NOT_ACCEPTED",
            message="Consent must be explicitly accepted (set accepted=true).",
        )

    if body.version_acknowledged != CURRENT_CONSENT_VERSION:
        raise ConflictError(
            error_code="CONSENT_VERSION_STALE",
            message=(
                "The consent text has been updated. "
                "Please review the new text and re-submit."
            ),
            details={
                "version_acknowledged": body.version_acknowledged,
                "current_version": CURRENT_CONSENT_VERSION,
            },
        )

    record = await consent_service.grant(
        workspace_id=workspace_id,
        user_id=user.id,
        ip=_client_ip(request),
        user_agent=_client_user_agent(request),
        version=CURRENT_CONSENT_VERSION,
        db=db,
    )

    return ConsentGrantResponse(
        accepted=record.accepted,
        version=record.version,
        granted_at=record.granted_at,
        current_text_version=CURRENT_CONSENT_VERSION,
    )


# ── DELETE: revoke + hard-delete ───────────────────────────────────────────


@router.delete(
    "",
    dependencies=[Depends(validate_csrf)],
    response_model=DeleteReportResponse,
)
async def delete_consent(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeleteReportResponse:
    """Revoke consent and synchronously hard-delete all face data.

    On success, returns counts and duration. On any failure inside
    hard_delete, the ServiceUnavailableError propagates with a
    FACE_HARD_DELETE_* error code; the caller's transaction rolls
    back and the consent remains active (see hard_delete.py docs
    for the full failure-mode analysis).
    """
    workspace_id = _resolve_workspace(user)
    await _check_rate_limit(str(user.id))

    report: DeleteReport | None = await consent_service.revoke(
        workspace_id=workspace_id,
        user_id=user.id,
        ip=_client_ip(request),
        user_agent=_client_user_agent(request),
        db=db,
    )

    if report is None:
        # No active consent existed. Return zeros so the client gets a
        # consistent response shape.
        return DeleteReportResponse(
            detection_count=0,
            cluster_count=0,
            qdrant_point_count=0,
            duration_ms=0,
        )

    return DeleteReportResponse(
        detection_count=report.detection_count,
        cluster_count=report.cluster_count,
        qdrant_point_count=report.qdrant_point_count,
        duration_ms=report.duration_ms,
    )
