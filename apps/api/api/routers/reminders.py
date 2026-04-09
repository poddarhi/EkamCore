"""Reminders endpoint: create user reminders with write-through to Apple Reminders.

POST /api/v1/reminders — create a new reminder (requires CSRF + auth)
"""

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.reminder import Reminder
from api.db.session import get_db
from api.errors import AuthorizationError, RateLimitError
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.schemas.reminder import ReminderCreateRequest, ReminderResponse
from api.services.audit import log_event
from api.services.redis_client import REDIS_DB_CACHE, get_redis
from api.services.write_through import send_to_apple_reminders

logger = structlog.get_logger()

_FLAG = require_flag("write_through_enabled")
_RATE_LIMIT_KEY_PREFIX = "rl:reminder_create:"
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW_SECS = 60

router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])


async def _check_rate_limit(user_id: str) -> None:
    """Enforce 10 writes/minute per user via Redis counter."""
    r = get_redis(REDIS_DB_CACHE)
    key = f"{_RATE_LIMIT_KEY_PREFIX}{user_id}"

    count_str = await r.get(key)
    if count_str is not None and int(count_str) >= _RATE_LIMIT_MAX:
        ttl = await r.ttl(key)
        raise RateLimitError(
            error_code="RATE_LIMIT_EXCEEDED",
            message=f"Too many reminder creations. Try again in {max(ttl, 1)} seconds.",
            details={"retry_after_seconds": max(ttl, 1)},
        )

    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, _RATE_LIMIT_WINDOW_SECS)
    await pipe.execute()


@router.post(
    "",
    dependencies=[_FLAG, Depends(validate_csrf)],
    status_code=201,
    response_model=ReminderResponse,
)
async def create_reminder(
    body: ReminderCreateRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReminderResponse:
    """Create a new reminder and push to Apple Reminders in the background."""
    if not user.workspace_ids:
        raise AuthorizationError(
            error_code="NO_WORKSPACE",
            message="User has no workspace.",
        )

    workspace_id = user.workspace_ids[0]

    # Rate limit
    await _check_rate_limit(str(user.id))

    # Create reminder
    reminder = Reminder(
        workspace_id=workspace_id,
        title=body.title,
        due_at=body.due_at,
        priority=body.priority,
        list_name=body.list_name,
        notes=body.notes,
        is_completed=False,
        write_through_status="pending",
        created_by=user.id,
    )
    db.add(reminder)
    await db.flush()

    # Audit log (atomic with the insert)
    await log_event(
        action="reminder_created",
        object_type="reminder",
        object_id=reminder.id,
        user_id=user.id,
        workspace_id=workspace_id,
        new_state={"title": reminder.title, "priority": reminder.priority},
        db=db,
    )

    # Schedule background write-through
    background_tasks.add_task(send_to_apple_reminders, reminder.id)

    logger.info(
        "reminder_created",
        reminder_id=str(reminder.id),
        workspace_id=str(workspace_id),
        user_id=str(user.id),
    )

    return ReminderResponse.model_validate(reminder)
