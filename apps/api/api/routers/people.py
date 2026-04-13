"""Trusted Persons / People Graph CRUD (S12-004).

Seven endpoints under ``/api/v1/people``:

  GET    /                           list (cursor pagination)
  GET    /:person_id                  detail
  POST   /                           create from cluster
  POST   /confirm-candidate          confirm a ranked candidate
  POST   /reject-cluster             reject a cluster (reversible)
  PATCH  /:person_id                  rename
  DELETE /:person_id                  soft delete

Authentication + face consent are enforced on every endpoint. The
workspace is always derived from the authenticated user's first
workspace_id — *never* from the request body — to eliminate
confused-deputy vectors against cluster/person ids.

Rate limits (per-user, Redis DB_CACHE):
  - reads:     120/minute
  - mutations: 30/minute

Mutations additionally require the standard double-submit CSRF
cookie via ``validate_csrf``.
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
from api.schemas.trusted_person import (
    ConfirmCandidateRequest,
    RejectClusterRequest,
    TrustedPersonCreateRequest,
    TrustedPersonListResponse,
    TrustedPersonRenameRequest,
    TrustedPersonResponse,
)
from api.services.face import consent_service, trusted_person_service
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/people", tags=["people"])


# ── Rate limiting ──────────────────────────────────────────────────────────

_READ_PREFIX = "rl:people_read:"
_READ_MAX = 120
_READ_WINDOW_SECS = 60

_WRITE_PREFIX = "rl:people_write:"
_WRITE_MAX = 30
_WRITE_WINDOW_SECS = 60


async def _check_rate_limit(
    user_id: UUID, *, prefix: str, max_calls: int, window_secs: int
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
    pipe.expire(key, window_secs)
    await pipe.execute()


async def _rate_limit_read(user_id: UUID) -> None:
    await _check_rate_limit(
        user_id,
        prefix=_READ_PREFIX,
        max_calls=_READ_MAX,
        window_secs=_READ_WINDOW_SECS,
    )


async def _rate_limit_write(user_id: UUID) -> None:
    await _check_rate_limit(
        user_id,
        prefix=_WRITE_PREFIX,
        max_calls=_WRITE_MAX,
        window_secs=_WRITE_WINDOW_SECS,
    )


# ── Consent resolution ────────────────────────────────────────────────────


async def _resolve_workspace(user: CurrentUser, db: AsyncSession) -> UUID:
    """Derive the user's workspace and re-check active face consent.

    Mirrors ``face_consent.py::_resolve_workspace`` + a consent check.
    We do NOT take workspace_id as a query param because people CRUD
    is always scoped to the caller's own workspace — a tampered query
    parameter is a confused-deputy vector.
    """
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


@router.get("", response_model=TrustedPersonListResponse)
async def list_people(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonListResponse:
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    rows, next_cursor = await trusted_person_service.list_persons(
        workspace_id=workspace_id,
        db=db,
        limit=limit,
        cursor=cursor,
    )
    return TrustedPersonListResponse(
        items=[TrustedPersonResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get("/{person_id}", response_model=TrustedPersonResponse)
async def get_person(
    person_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    row = await trusted_person_service.get_person(
        person_id=person_id, workspace_id=workspace_id, db=db
    )
    return TrustedPersonResponse.model_validate(row)


@router.post(
    "",
    dependencies=[Depends(validate_csrf)],
    status_code=201,
    response_model=TrustedPersonResponse,
)
async def create_person(
    body: TrustedPersonCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    person = await trusted_person_service.create_from_cluster(
        cluster_id=body.cluster_id,
        workspace_id=workspace_id,
        user_id=user.id,
        display_name=body.display_name,
        canonical_contact_id=body.canonical_contact_id,
        trust_source="manual",
        db=db,
    )
    return TrustedPersonResponse.model_validate(person)


@router.post(
    "/confirm-candidate",
    dependencies=[Depends(validate_csrf)],
    response_model=TrustedPersonResponse,
)
async def confirm_candidate(
    body: ConfirmCandidateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    person = await trusted_person_service.confirm_candidate(
        cluster_id=body.cluster_id,
        contact_id=body.contact_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
    return TrustedPersonResponse.model_validate(person)


@router.post(
    "/reject-cluster",
    dependencies=[Depends(validate_csrf)],
    status_code=204,
    response_model=None,
)
async def reject_cluster(
    body: RejectClusterRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await trusted_person_service.reject_cluster(
        cluster_id=body.cluster_id,
        workspace_id=workspace_id,
        user_id=user.id,
        reason=body.reason,
        db=db,
    )


@router.patch(
    "/{person_id}",
    dependencies=[Depends(validate_csrf)],
    response_model=TrustedPersonResponse,
)
async def rename_person(
    person_id: UUID,
    body: TrustedPersonRenameRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    person = await trusted_person_service.rename(
        person_id=person_id,
        workspace_id=workspace_id,
        user_id=user.id,
        new_name=body.display_name,
        db=db,
    )
    return TrustedPersonResponse.model_validate(person)


@router.delete(
    "/{person_id}",
    dependencies=[Depends(validate_csrf)],
    status_code=204,
    response_model=None,
)
async def delete_person(
    person_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await trusted_person_service.delete(
        person_id=person_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
