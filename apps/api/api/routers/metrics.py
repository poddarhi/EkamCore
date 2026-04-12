"""Metrics API endpoints (G-15 / ART-27).

Admin-only access to locally-collected telemetry. Never sends data
externally — all metrics stay on the user's Mac.

Endpoints:
  GET /api/v1/metrics                — historical metrics (filtered by period)
  GET /api/v1/metrics/current        — live system snapshot
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.schemas.auth import CurrentUser
from api.schemas.metrics import CurrentMetricsSnapshot, MetricEntry, MetricsResponse
from api.services import metrics_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


def _require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise AuthorizationError(
            error_code="ADMIN_REQUIRED",
            message="Admin role required for metrics access.",
        )
    return user


@router.get("", response_model=MetricsResponse)
async def list_metrics(
    workspace_id: UUID = Query(..., description="Workspace to query"),
    metric_key: str | None = Query(
        default=None, description="Filter by metric_key prefix (e.g. 'api_latency', 'daily')"
    ),
    start: datetime | None = Query(default=None, description="Inclusive period_start lower bound"),
    end: datetime | None = Query(default=None, description="Inclusive period_end upper bound"),
    period: str = Query(
        default="day",
        pattern="^(hour|day|week)$",
        description="Aggregation period hint (informational)",
    ),
    limit: int = Query(default=1000, ge=1, le=10000),
    admin: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> MetricsResponse:
    """Return stored metrics for the specified workspace and time range."""
    if workspace_id not in admin.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    metrics = await metrics_service.query_metrics(
        db=db,
        workspace_id=workspace_id,
        metric_key=metric_key,
        start=start,
        end=end,
        limit=limit,
    )

    entries = [
        MetricEntry(
            id=m.id,
            metric_key=m.metric_key,
            metric_value=m.metric_value,
            period_start=m.period_start,
            period_end=m.period_end,
            workspace_id=m.workspace_id,
            created_at=m.created_at,
        )
        for m in metrics
    ]

    logger.info(
        "metrics_queried",
        admin_user_id=str(admin.id),
        workspace_id=str(workspace_id),
        count=len(entries),
        period=period,
    )

    return MetricsResponse(metrics=entries, count=len(entries), period=period)


@router.get("/current", response_model=CurrentMetricsSnapshot)
async def get_current_metrics(
    workspace_id: UUID = Query(..., description="Workspace to query"),
    admin: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> CurrentMetricsSnapshot:
    """Return a live snapshot of current system metrics (not stored)."""
    if workspace_id not in admin.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    snapshot = await metrics_service.get_current_snapshot(db=db, workspace_id=workspace_id)

    logger.info(
        "metrics_snapshot_queried",
        admin_user_id=str(admin.id),
        workspace_id=str(workspace_id),
    )

    return CurrentMetricsSnapshot(**snapshot)
