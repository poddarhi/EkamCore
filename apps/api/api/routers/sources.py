import structlog
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from api.db.session import get_db
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.schemas.source import SourceCreate, SourceListResponse, SourceResponse, SourceUpdate
from api.services import source_service

logger = structlog.get_logger()

_FLAG = require_flag("sources_management_enabled")

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("", dependencies=[_FLAG], response_model=SourceListResponse)
async def list_sources(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SourceListResponse:
    items, next_cursor = await source_service.list_sources(
        workspace_ids=user.workspace_ids,
        db=db,
        cursor=cursor,
        limit=limit,
    )
    return SourceListResponse(
        items=[SourceResponse.model_validate(s) for s in items],
        next_cursor=next_cursor,
    )


@router.post("", dependencies=[_FLAG, Depends(validate_csrf)], status_code=201, response_model=SourceResponse)
async def create_source(
    body: SourceCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SourceResponse:
    if not user.workspace_ids:
        from api.errors import AuthorizationError
        raise AuthorizationError(error_code="NO_WORKSPACE", message="User has no workspace.")

    source = await source_service.create_source(
        workspace_id=user.workspace_ids[0],
        registered_by=user.id,
        body=body,
        db=db,
    )
    return SourceResponse.model_validate(source)


@router.patch("/{source_id}", dependencies=[_FLAG, Depends(validate_csrf)], response_model=SourceResponse)
async def update_source(
    source_id: UUID,
    body: SourceUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SourceResponse:
    source = await source_service.update_source(
        source_id=source_id,
        workspace_ids=user.workspace_ids,
        body=body,
        db=db,
    )
    return SourceResponse.model_validate(source)


@router.delete("/{source_id}", dependencies=[_FLAG, Depends(validate_csrf)], status_code=204)
async def delete_source(
    source_id: UUID,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await source_service.delete_source(
        source_id=source_id,
        workspace_ids=user.workspace_ids,
        db=db,
    )
