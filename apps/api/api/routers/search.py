"""Search endpoint: text search across calendar, reminders, contacts.

GET /api/v1/search?q=...&type=...&date_from=...&date_to=...&per_page=...&cursor=...
"""

from __future__ import annotations

import time
from datetime import datetime
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
from api.schemas.search import PaginationInfo, SearchResponse
from api.services.query.search import SearchType, search_all

logger = structlog.get_logger()

_FLAG = require_flag("search_basic_enabled")

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", dependencies=[_FLAG], response_model=SearchResponse)
async def get_search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    workspace_id: UUID = Query(..., description="Workspace to search"),
    type: Literal["calendar", "reminder", "contact", "file", "photo", "all"] = Query(
        "all", description="Type filter"
    ),
    date_from: datetime | None = Query(None, description="Filter events from this date"),
    date_to: datetime | None = Query(None, description="Filter events to this date"),
    has_gps: bool | None = Query(None, description="Filter photos with GPS coordinates"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    cursor: int = Query(0, ge=0, description="Offset cursor for pagination"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search across calendar events, reminders, and contacts."""
    if workspace_id not in user.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    t0 = time.perf_counter()

    types: list[SearchType] | None = None
    if type != "all":
        types = [type]

    cards, facets = await search_all(
        q,
        workspace_id,
        db,
        types=types,
        date_from=date_from,
        date_to=date_to,
        has_gps=has_gps,
        limit=per_page + 1,  # Fetch one extra to detect has_more
        offset=cursor,
    )

    has_more = len(cards) > per_page
    result_cards = cards[:per_page]

    latency_ms = int((time.perf_counter() - t0) * 1000)
    total_results = sum(facets.values())

    logger.info(
        "search_completed",
        query_length=len(q),
        workspace_id=str(workspace_id),
        type_filter=type,
        result_count=len(result_cards),
        total_results=total_results,
        latency_ms=latency_ms,
    )

    return SearchResponse(
        data=[card.model_dump() for card in result_cards],
        pagination=PaginationInfo(
            cursor=cursor + len(result_cards),
            has_more=has_more,
        ),
        facets=facets,
    )
