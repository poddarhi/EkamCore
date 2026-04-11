"""In-app notification service (G-09 / ART-20).

Creates, lists, and marks notifications as read.  Notifications are
workspace-isolated and per-user.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.notification import Notification

logger = structlog.get_logger()


class NotificationType(str, enum.Enum):
    INGESTION_COMPLETE = "INGESTION_COMPLETE"
    INGESTION_FAILED = "INGESTION_FAILED"
    BACKUP_COMPLETE = "BACKUP_COMPLETE"
    BACKUP_FAILED = "BACKUP_FAILED"
    SYSTEM_DEGRADED = "SYSTEM_DEGRADED"
    SYSTEM_RECOVERED = "SYSTEM_RECOVERED"


async def create_notification(
    user_id: UUID,
    workspace_id: UUID,
    type: NotificationType,
    title: str,
    message: str,
    db: AsyncSession,
    metadata: dict[str, Any] | None = None,
) -> Notification:
    """Create a new notification for a user in a workspace."""
    notif = Notification(
        user_id=user_id,
        workspace_id=workspace_id,
        type=type.value,
        title=title,
        message=message,
        metadata_json=metadata,
    )
    db.add(notif)
    await db.flush()

    logger.info(
        "notification_created",
        notification_type=type.value,
        workspace_id=str(workspace_id),
    )
    return notif


async def get_notifications(
    user_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Notification], int]:
    """Get notifications for a user, optionally filtered to unread only.

    Returns (notifications, total_count).
    """
    conditions = [
        Notification.user_id == user_id,
        Notification.workspace_id == workspace_id,
    ]
    if unread_only:
        conditions.append(Notification.is_read.is_(False))

    where = and_(*conditions)

    count_stmt = select(func.count()).select_from(Notification).where(where)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Notification)
        .where(where)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await db.execute(stmt)).scalars().all())

    return rows, total


async def get_unread_count(
    user_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> int:
    """Return the count of unread notifications."""
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.workspace_id == workspace_id,
            Notification.is_read.is_(False),
        )
    )
    return (await db.execute(stmt)).scalar_one()


async def mark_read(
    notification_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> bool:
    """Mark a single notification as read. Returns True if updated."""
    stmt = (
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


async def mark_all_read(
    user_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> int:
    """Mark all unread notifications as read. Returns count updated."""
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.workspace_id == workspace_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    result = await db.execute(stmt)
    return result.rowcount
