"""Notification API endpoints (G-09).

GET  /api/v1/notifications        → paginated list (unread_only filter)
PATCH /api/v1/notifications/:id/read → mark single as read
POST /api/v1/notifications/mark-all-read → mark all as read
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError, NotFoundError
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.schemas.auth import CurrentUser
from api.services.notification_service import (
    get_notifications,
    get_unread_count,
    mark_all_read,
    mark_read,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class NotificationItem(BaseModel):
    id: str
    type: str
    title: str
    message: str
    metadata: dict | None = None
    is_read: bool
    created_at: str


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItem]
    unread_count: int
    total: int


def _workspace_id(user: CurrentUser) -> UUID:
    if not user.workspace_ids:
        raise AuthorizationError(error_code="NO_WORKSPACE", message="No workspace found.")
    return user.workspace_ids[0]


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False, description="Filter to unread only"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    ws_id = _workspace_id(user)
    rows, total = await get_notifications(user.id, ws_id, db, unread_only=unread_only, limit=limit, offset=offset)
    unread = await get_unread_count(user.id, ws_id, db)

    return NotificationListResponse(
        notifications=[
            NotificationItem(
                id=str(n.id),
                type=n.type,
                title=n.title,
                message=n.message,
                metadata=n.metadata_json,
                is_read=n.is_read,
                created_at=n.created_at.isoformat() if n.created_at else "",
            )
            for n in rows
        ],
        unread_count=unread,
        total=total,
    )


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    updated = await mark_read(notification_id, user.id, db)
    if not updated:
        raise NotFoundError(error_code="NOT_FOUND", message="Notification not found or already read.")
    await db.commit()
    return {"status": "read"}


@router.post(
    "/mark-all-read",
    dependencies=[Depends(validate_csrf)],
)
async def mark_all_notifications_read(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ws_id = _workspace_id(user)
    count = await mark_all_read(user.id, ws_id, db)
    await db.commit()
    logger.info("notifications_all_marked_read", user_id=str(user.id), count=count)
    return {"status": "all_read", "count": count}
