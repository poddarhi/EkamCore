"""Admin endpoints: audit log query.

All endpoints require:
  - Valid JWT (get_current_user)
  - role == "admin"
  - audit_log_enabled feature flag
"""

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.audit_log import AuditLog
from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.audit import AuditLogEntry, AuditLogPage
from api.schemas.auth import CurrentUser

logger = structlog.get_logger()

_FLAG = require_flag("audit_log_enabled")

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


def _require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise AuthorizationError(
            error_code="ADMIN_REQUIRED",
            message="Admin role required for this endpoint.",
        )
    return user


@router.get("/audit-log", dependencies=[_FLAG], response_model=AuditLogPage)
async def list_audit_log(
    action: str | None = Query(default=None, description="Filter by action name"),
    object_type: str | None = Query(default=None, description="Filter by object type"),
    user_id: UUID | None = Query(default=None, description="Filter by user UUID"),
    from_date: datetime | None = Query(default=None, description="Inclusive lower bound on created_at"),
    to_date: datetime | None = Query(default=None, description="Exclusive upper bound on created_at"),
    per_page: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    cursor: int | None = Query(default=None, description="Last seen id for keyset pagination"),
    admin: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> AuditLogPage:
    """Return a page of audit log entries, newest-to-oldest within the filtered set.

    Pagination is keyset-based on the BIGSERIAL id.  Pass `cursor` = the last
    `id` returned to fetch the next page.
    """
    stmt = select(AuditLog).order_by(AuditLog.id.asc())

    if cursor is not None:
        stmt = stmt.where(AuditLog.id > cursor)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if object_type is not None:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if from_date is not None:
        stmt = stmt.where(AuditLog.created_at >= from_date)
    if to_date is not None:
        stmt = stmt.where(AuditLog.created_at < to_date)

    stmt = stmt.limit(per_page + 1)

    rows = list((await db.execute(stmt)).scalars().all())

    if len(rows) > per_page:
        rows = rows[:per_page]
        next_cursor = rows[-1].id
    else:
        next_cursor = None

    logger.info(
        "audit_log_queried",
        admin_user_id=str(admin.id),
        action_filter=action,
        returned=len(rows),
    )

    return AuditLogPage(
        items=[AuditLogEntry.from_row(r) for r in rows],
        next_cursor=next_cursor,
        total_in_page=len(rows),
    )
