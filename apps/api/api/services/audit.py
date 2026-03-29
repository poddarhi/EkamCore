"""Audit service: append-only security event logging.

Two write paths:

  log_event(db=db, ...)
      Adds the audit row to the *caller's existing transaction*.  Use on
      success paths where the audit entry should commit atomically with the
      main operation (login success, logout, token refresh, source CRUD).

  log_event_now(...)
      Opens its own session and commits immediately.  Use on failure paths
      where the caller's transaction will be rolled back (login failure,
      account locked) so the audit entry must survive independently.

PII rules (enforced by callers):
  - Never pass passwords, plaintext tokens, emails, or bearer credentials in
    old_state / new_state / metadata.
  - user_id (UUID) is safe to store; it is not PII under our threat model.
  - source_ip is stored as supplied by the request layer.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.audit_log import AuditLog

logger = structlog.get_logger()


async def log_event(
    *,
    action: str,
    object_type: str,
    db: AsyncSession,
    object_id: UUID | None = None,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    old_state: dict | None = None,
    new_state: dict | None = None,
    ip: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Append an audit event within the caller's transaction.

    Returns as soon as the row is flushed (no I/O beyond a single INSERT).
    Commits and rolls back with the caller's session.
    """
    entry = AuditLog(
        user_id=user_id,
        workspace_id=workspace_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        old_state=old_state,
        new_state=new_state,
        metadata_json=metadata,
        source_ip=ip,
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "audit_event",
        action=action,
        object_type=object_type,
        user_id=str(user_id) if user_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
    )


async def log_event_now(
    *,
    action: str,
    object_type: str,
    object_id: UUID | None = None,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    old_state: dict | None = None,
    new_state: dict | None = None,
    ip: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Append an audit event using an independent session that commits immediately.

    Use on failure paths (login_failure, account_locked) where the caller's
    transaction may be rolled back.  Swallows DB errors so that an audit
    write failure never masks the original error returned to the caller.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from api.config import settings

    # Use NullPool so there is no per-engine connection pool that could be
    # tied to a different event loop or left open after the call completes.
    _eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    _factory = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with _factory() as db:
            entry = AuditLog(
                user_id=user_id,
                workspace_id=workspace_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                old_state=old_state,
                new_state=new_state,
                metadata_json=metadata,
                source_ip=ip,
            )
            db.add(entry)
            await db.commit()
        logger.info(
            "audit_event",
            action=action,
            object_type=object_type,
            user_id=str(user_id) if user_id else None,
        )
    except Exception:
        logger.warning("audit_log_write_failed", action=action, exc_info=True)
    finally:
        await _eng.dispose()
