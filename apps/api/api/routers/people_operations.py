"""Merge / split / undo endpoints for the People Graph (S12-006).

Mounted under ``/api/v1/people`` so these actions live alongside
the base CRUD from S12-004. Every endpoint is consent-gated via
``_resolve_workspace`` (mirrors routers/people.py), CSRF-protected,
and rate-limited 30/min/user.

  POST   /merge                                  multi-merge
  POST   /{person_id}/split                       split off faces
  POST   /operations/undo-last                   undo latest for workspace
  POST   /operations/{operation_id}/undo         undo specific
  GET    /operations                              history (last 50)
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
from api.schemas.people_operations import (
    MergeRequest,
    OperationListResponse,
    OperationResponse,
    SplitRequest,
    UndoResponse,
)
from api.schemas.trusted_person import TrustedPersonResponse
from api.services.face import (
    consent_service,
    merge_service,
    split_service,
    undo_service,
)
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/people", tags=["people-operations"])


_RL_PREFIX = "rl:people_ops:"
_RL_MAX = 30
_RL_WINDOW = 60


async def _rate_limit(user_id: UUID) -> None:
    r = get_redis(REDIS_DB_CACHE)
    key = f"{_RL_PREFIX}{user_id}"
    count_str = await r.get(key)
    if count_str is not None and int(count_str) >= _RL_MAX:
        ttl = await r.ttl(key)
        raise RateLimitError(
            error_code="RATE_LIMIT_EXCEEDED",
            message=f"Too many requests. Try again in {max(ttl, 1)} seconds.",
            details={"retry_after_seconds": max(ttl, 1)},
        )
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, _RL_WINDOW)
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


@router.post(
    "/merge",
    dependencies=[Depends(validate_csrf)],
    response_model=TrustedPersonResponse,
)
async def merge_persons(
    body: MergeRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit(user.id)
    workspace_id = await _resolve_workspace(user, db)
    keeper = await merge_service.merge_persons(
        person_ids=body.person_ids,
        keeper_id=body.keeper_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
    return TrustedPersonResponse.model_validate(keeper)


@router.post(
    "/{person_id}/split",
    dependencies=[Depends(validate_csrf)],
    response_model=TrustedPersonResponse,
)
async def split_person(
    person_id: UUID,
    body: SplitRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit(user.id)
    workspace_id = await _resolve_workspace(user, db)
    _, new_person = await split_service.split_person(
        person_id=person_id,
        face_detection_ids=body.face_detection_ids,
        new_display_name=body.new_display_name,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
    return TrustedPersonResponse.model_validate(new_person)


@router.post(
    "/operations/undo-last",
    dependencies=[Depends(validate_csrf)],
    response_model=UndoResponse,
)
async def undo_last(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UndoResponse:
    await _rate_limit(user.id)
    workspace_id = await _resolve_workspace(user, db)
    result = await undo_service.undo_last_operation(
        workspace_id=workspace_id, user_id=user.id, db=db
    )
    return UndoResponse(
        operation_id=result.operation_id,
        operation_type=result.operation_type,
    )


@router.post(
    "/operations/{operation_id}/undo",
    dependencies=[Depends(validate_csrf)],
    response_model=UndoResponse,
)
async def undo_operation(
    operation_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UndoResponse:
    await _rate_limit(user.id)
    workspace_id = await _resolve_workspace(user, db)
    result = await undo_service.undo_specific_operation(
        operation_id=operation_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
    return UndoResponse(
        operation_id=result.operation_id,
        operation_type=result.operation_type,
    )


@router.get("/operations", response_model=OperationListResponse)
async def list_operations(
    limit: int = Query(default=50, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OperationListResponse:
    await _rate_limit(user.id)
    workspace_id = await _resolve_workspace(user, db)
    rows = await undo_service.list_recent_operations(
        workspace_id=workspace_id, db=db, limit=limit
    )
    return OperationListResponse(
        items=[OperationResponse.model_validate(r) for r in rows]
    )
