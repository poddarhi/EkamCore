"""User-initiated historical face backfill endpoints (S11-007).

Three endpoints under /api/v1/settings/face-clustering/backfill:

  POST   — start a backfill run for the caller's workspace
  GET    — return the current or most recent job for the caller's workspace
  DELETE — request cancellation of the currently running job

All endpoints:
  - Require authentication (``get_current_user``)
  - Require active face consent (enforced inline via ``is_consent_active``,
    matching the pattern in the consent router — we do not use the
    ``require_face_consent`` dependency because that dependency pulls
    workspace_id from a query parameter and these endpoints instead
    derive it from the authenticated user to avoid confused-deputy
    attacks)
  - POST/DELETE require CSRF
  - POST is rate limited 1/hour/workspace (kicking off a backfill is
    expensive — a user mashing the button shouldn't queue ten of them)

The state machine:

    (none)  ──(POST)──► running  ──(natural end)──► completed
                         │                    └──► failed      (worker crashed)
                         └──(DELETE)─────────────► cancelled
                         └──(consent revoked)────► cancelled

GET returns the latest job in any state so the UI can render a
"last run: completed 5 minutes ago" summary after a run finishes.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import (
    AuthorizationError,
    FaceConsentRequiredError,
    NotFoundError,
    RateLimitError,
)
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.schemas.auth import CurrentUser
from api.services.face import backfill_service, consent_service
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/settings/face-clustering/backfill",
    tags=["face-backfill"],
)

# Rate limit: 1 start per hour per workspace. POST is the only rate-limited
# action — GET is cheap and DELETE is a safety valve.
_START_RATE_LIMIT_PREFIX = "rl:face_backfill_start:"
_START_RATE_LIMIT_WINDOW_SECS = 3600
_START_RATE_LIMIT_MAX = 1


def _resolve_workspace(user: CurrentUser) -> UUID:
    """Return the workspace to apply this backfill action against.

    Mirrors the consent router: users typically have one workspace
    in Phase 3, and we never accept workspace_id as a tampering-prone
    query parameter here.
    """
    if not user.workspace_ids:
        raise AuthorizationError(
            error_code="NO_WORKSPACE",
            message="User has no workspace.",
        )
    return user.workspace_ids[0]


async def _require_consent(
    workspace_id: UUID, db: AsyncSession
) -> None:
    """Raise FaceConsentRequiredError if no active consent exists."""
    if not await consent_service.is_consent_active(workspace_id, db):
        raise FaceConsentRequiredError(
            error_code="FACE_CONSENT_REQUIRED",
            message=(
                "Face clustering requires your explicit consent. "
                "Enable it in Settings \u2192 Photo Intelligence."
            ),
        )


async def _check_start_rate_limit(workspace_id: UUID) -> None:
    """Enforce 1 backfill start per hour per workspace."""
    r = get_redis(REDIS_DB_CACHE)
    key = f"{_START_RATE_LIMIT_PREFIX}{workspace_id}"
    count_str = await r.get(key)
    if count_str is not None and int(count_str) >= _START_RATE_LIMIT_MAX:
        ttl = await r.ttl(key)
        raise RateLimitError(
            error_code="RATE_LIMIT_EXCEEDED",
            message=(
                f"Too many backfill starts. Try again in "
                f"{max(ttl, 1)} seconds."
            ),
            details={"retry_after_seconds": max(ttl, 1)},
        )
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, _START_RATE_LIMIT_WINDOW_SECS)
    await pipe.execute()


# ── Response model ─────────────────────────────────────────────────────────


class BackfillJobResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    state: str  # "running" | "completed" | "failed" | "cancelled"
    started_at: datetime
    finished_at: datetime | None = None
    total_photos: int
    processed_photos: int
    failed_photos: int
    error_message: str | None = None


def _to_response(job) -> BackfillJobResponse:
    return BackfillJobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        state=job.state,
        started_at=job.started_at,
        finished_at=job.finished_at,
        total_photos=job.total_photos,
        processed_photos=job.processed_photos,
        failed_photos=job.failed_photos,
        error_message=job.error_message,
    )


# ── POST: start ────────────────────────────────────────────────────────────


@router.post(
    "",
    dependencies=[Depends(validate_csrf)],
    response_model=BackfillJobResponse,
    status_code=202,
)
async def start_backfill(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BackfillJobResponse:
    """Start a face backfill for the caller's workspace.

    Returns 202 + the new job row on success. The worker runs
    asynchronously — the client polls GET for progress.
    """
    workspace_id = _resolve_workspace(user)
    await _require_consent(workspace_id, db)
    await _check_start_rate_limit(workspace_id)

    job = await backfill_service.start_backfill(
        workspace_id=workspace_id, db=db
    )
    await db.commit()
    return _to_response(job)


# ── GET: current/most recent job ───────────────────────────────────────────


@router.get("", response_model=BackfillJobResponse | None)
async def get_backfill_status(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BackfillJobResponse | None:
    """Return the most recent job for this workspace, or ``null`` if
    no backfill has ever been run.

    Consent is still required — a revoked user shouldn't be able to
    read historical job rows because they indirectly reveal photo
    counts.
    """
    workspace_id = _resolve_workspace(user)
    await _require_consent(workspace_id, db)

    job = await backfill_service.get_latest_job(workspace_id, db)
    if job is None:
        return None
    return _to_response(job)


# ── DELETE: cancel ─────────────────────────────────────────────────────────


@router.delete(
    "",
    dependencies=[Depends(validate_csrf)],
    response_model=BackfillJobResponse,
)
async def cancel_backfill(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BackfillJobResponse:
    """Request cancellation of the currently running backfill.

    Returns the job row in its cancelled state. 404 if no running
    job exists.
    """
    workspace_id = _resolve_workspace(user)
    await _require_consent(workspace_id, db)

    try:
        job = await backfill_service.cancel_backfill(workspace_id, db)
    except NotFoundError:
        raise
    await db.commit()
    return _to_response(job)
