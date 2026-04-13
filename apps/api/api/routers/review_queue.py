"""Review Queue API — surface clusters awaiting user confirmation (S12-005).

Three read-shaped endpoints under ``/api/v1/review-queue``:

  GET  /                       list pending clusters, sorted by score
  GET  /:cluster_id            full detail incl. all member photos
  POST /:cluster_id/skip       tag cluster as "skipped" for this user (24h)

Confirm/reject actions are intentionally *not* here — they live on
the S12-004 People endpoints (``POST /api/v1/people/confirm-candidate``
and ``POST /api/v1/people/reject-cluster``) so the audit trail for
state changes has exactly one enforcement point.

Consent is re-checked on every call. The workspace is derived from
the authenticated user's first workspace_id; we never accept a
workspace_id query parameter on this endpoint to avoid a confused
deputy vector.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import (
    AuthorizationError,
    FaceConsentRequiredError,
    RateLimitError,
)
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.schemas.auth import CurrentUser
from api.schemas.review_queue import (
    ReviewQueueDetailResponse,
    ReviewQueueListResponse,
)
from api.services.face import consent_service, review_queue
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/review-queue", tags=["review-queue"])


# ── Rate limiting (reuses People's read/write buckets conceptually) ───────

_READ_PREFIX = "rl:review_queue_read:"
_READ_MAX = 120
_WRITE_PREFIX = "rl:review_queue_write:"
_WRITE_MAX = 30
_WINDOW_SECS = 60


async def _check_rate_limit(
    user_id: UUID, *, prefix: str, max_calls: int
) -> None:
    r = get_redis(REDIS_DB_CACHE)
    key = f"{prefix}{user_id}"
    count_str = await r.get(key)
    if count_str is not None and int(count_str) >= max_calls:
        ttl = await r.ttl(key)
        raise RateLimitError(
            error_code="RATE_LIMIT_EXCEEDED",
            message=f"Too many requests. Try again in {max(ttl, 1)} seconds.",
            details={"retry_after_seconds": max(ttl, 1)},
        )
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, _WINDOW_SECS)
    await pipe.execute()


async def _resolve_workspace(user: CurrentUser, db: AsyncSession) -> UUID:
    if not user.workspace_ids:
        raise AuthorizationError(
            error_code="NO_WORKSPACE",
            message="User has no workspace.",
        )
    workspace_id = user.workspace_ids[0]
    if not await consent_service.is_consent_active(workspace_id, db):
        raise FaceConsentRequiredError(
            error_code="FACE_CONSENT_REQUIRED",
            message=(
                "Face clustering requires your explicit consent. "
                "Enable it in Settings \u2192 Photo Intelligence."
            ),
        )
    return workspace_id


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("", response_model=ReviewQueueListResponse)
async def list_review_queue(
    confidence: str | None = Query(
        default=None,
        pattern="^(high|medium|low|none)$",
    ),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueListResponse:
    await _check_rate_limit(user.id, prefix=_READ_PREFIX, max_calls=_READ_MAX)
    workspace_id = await _resolve_workspace(user, db)
    items, next_cursor = await review_queue.list_pending(
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
        confidence_filter=confidence,
        limit=limit,
        cursor=cursor,
    )
    return ReviewQueueListResponse(items=items, next_cursor=next_cursor)


@router.get("/{cluster_id}", response_model=ReviewQueueDetailResponse)
async def get_review_item(
    cluster_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueDetailResponse:
    await _check_rate_limit(user.id, prefix=_READ_PREFIX, max_calls=_READ_MAX)
    workspace_id = await _resolve_workspace(user, db)
    return await review_queue.get_item(
        cluster_id=cluster_id, workspace_id=workspace_id, db=db
    )


@router.post(
    "/{cluster_id}/skip",
    dependencies=[Depends(validate_csrf)],
    status_code=204,
    response_model=None,
)
async def skip_review_item(
    cluster_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _check_rate_limit(user.id, prefix=_WRITE_PREFIX, max_calls=_WRITE_MAX)
    workspace_id = await _resolve_workspace(user, db)
    await review_queue.skip(
        cluster_id=cluster_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
