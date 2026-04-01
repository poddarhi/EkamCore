"""Today endpoint: returns a ResponseEnvelope of prioritised cards for the current day."""

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.schemas.envelope import ResponseEnvelope
from api.services import today as today_service

logger = structlog.get_logger()

_FLAG = require_flag("today_enabled")

router = APIRouter(prefix="/api/v1/today", tags=["today"])


@router.get("", dependencies=[_FLAG], response_model=ResponseEnvelope)
async def get_today(
    workspace_id: UUID = Query(..., description="Workspace to query"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope:
    """Return today's calendar events, reminders, and status as prioritised cards.

    All cards are sorted by priority_score descending.
    """
    if workspace_id not in user.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    envelope = await today_service.assemble_today(
        workspace_id=workspace_id,
        db=db,
    )

    logger.info(
        "today_assembled",
        workspace_id=str(workspace_id),
        card_count=len(envelope.cards),
    )
    return envelope
