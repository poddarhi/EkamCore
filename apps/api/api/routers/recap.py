"""Recap endpoint: returns a ResponseEnvelope of cards for a past day or week."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

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
from api.services.recap.generator import generate_recap

logger = structlog.get_logger()

_FLAG = require_flag("recap_enabled")

router = APIRouter(prefix="/api/v1/recap", tags=["recap"])


@router.get("", dependencies=[_FLAG], response_model=ResponseEnvelope)
async def get_recap(
    workspace_id: UUID = Query(..., description="Workspace to query"),
    period: Literal["daily", "weekly"] = Query("daily", description="Recap period"),
    date_param: date | None = Query(
        None,
        alias="date",
        description="Target date (YYYY-MM-DD). Defaults to yesterday.",
    ),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope:
    """Return a recap of events, completed reminders, and new overdue items.

    Daily: cards for a single date.
    Weekly: cards aggregated over 7 days ending on the target date.
    """
    if workspace_id not in user.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    envelope = await generate_recap(
        workspace_id=workspace_id,
        db=db,
        period=period,
        target_date=date_param,
    )

    logger.info(
        "recap_served",
        workspace_id=str(workspace_id),
        period=period,
        target_date=str(date_param),
        card_count=len(envelope.cards),
    )
    return envelope
