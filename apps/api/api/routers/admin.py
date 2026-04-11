"""Admin endpoints: audit log query, diagnostics export, ingestion jobs.

All endpoints require:
  - Valid JWT (get_current_user)
  - role == "admin"
  - audit_log_enabled feature flag
"""

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.db.models.audit_log import AuditLog
from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.source import Source
from api.db.session import get_db
from api.errors import AuthorizationError, NotFoundError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.audit import AuditLogEntry, AuditLogPage
from api.schemas.auth import CurrentUser
from api.services.diagnostics import build_diagnostics_zip
from api.services.ingestion.state_machine import TERMINAL_STAGES

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


@router.get("/diagnostics")
async def get_diagnostics(
    admin: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download a ZIP file containing system diagnostics.

    Admin-only. Contains system info, service health, container stats,
    audit log summary (counts only), and sanitized error logs.
    All PII is stripped before inclusion.
    """
    zip_bytes = await build_diagnostics_zip(db)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ekamcore_diagnostics_{timestamp}.zip"

    logger.info("diagnostics_downloaded", admin_user_id=str(admin.id))

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Ingestion jobs
# ---------------------------------------------------------------------------

_ACTIVE_STAGES = {
    "DISCOVERED", "FINGERPRINTED", "METADATA_EXTRACTED",
    "TEXT_EXTRACTED", "OCR_COMPLETED", "EMBEDDING_QUEUED", "EMBEDDED",
}


def _job_dict(state: IngestionState) -> dict:
    """Serialize an IngestionState row into a job dict for the API response."""
    f = state.file
    elapsed = None
    if state.created_at and state.updated_at:
        elapsed = int((state.updated_at - state.created_at).total_seconds())

    return {
        "id": str(state.id),
        "file_id": str(state.file_id),
        "filename": f.filename if f else "unknown",
        "source_name": f.source.name if f and f.source else "unknown",
        "current_stage": state.current_stage,
        "stages_completed": state.stages_completed,
        "retry_count": state.retry_count,
        "error_message": state.error_message,
        "elapsed_seconds": elapsed,
        "created_at": state.created_at.isoformat() if state.created_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


@router.get("/jobs")
async def list_jobs(
    admin: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return ingestion jobs grouped by status.

    Groups:
      - active: currently processing (not in terminal state)
      - recently_completed: last 20 COMPLETED
      - failed: last 50 FAILED
      - skipped: last 20 SKIPPED
    """
    # Active jobs
    active_stmt = (
        select(IngestionState)
        .where(IngestionState.current_stage.in_(_ACTIVE_STAGES))
        .options(selectinload(IngestionState.file).selectinload(File.source))
        .order_by(IngestionState.updated_at.desc())
        .limit(100)
    )
    active_rows = list((await db.execute(active_stmt)).scalars().all())

    # Recently completed
    completed_stmt = (
        select(IngestionState)
        .where(IngestionState.current_stage == "COMPLETED")
        .options(selectinload(IngestionState.file).selectinload(File.source))
        .order_by(IngestionState.updated_at.desc())
        .limit(20)
    )
    completed_rows = list((await db.execute(completed_stmt)).scalars().all())

    # Failed
    failed_stmt = (
        select(IngestionState)
        .where(IngestionState.current_stage == "FAILED")
        .options(selectinload(IngestionState.file).selectinload(File.source))
        .order_by(IngestionState.updated_at.desc())
        .limit(50)
    )
    failed_rows = list((await db.execute(failed_stmt)).scalars().all())

    # Skipped
    skipped_stmt = (
        select(IngestionState)
        .where(IngestionState.current_stage == "SKIPPED")
        .options(selectinload(IngestionState.file).selectinload(File.source))
        .order_by(IngestionState.updated_at.desc())
        .limit(20)
    )
    skipped_rows = list((await db.execute(skipped_stmt)).scalars().all())

    logger.info("jobs_listed", admin_user_id=str(admin.id))

    return {
        "active": [_job_dict(r) for r in active_rows],
        "recently_completed": [_job_dict(r) for r in completed_rows],
        "failed": [_job_dict(r) for r in failed_rows],
        "skipped": [_job_dict(r) for r in skipped_rows],
    }


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(
    job_id: UUID = Path(..., description="IngestionState ID to retry"),
    admin: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset a FAILED job to DISCOVERED so it is re-processed.

    Returns 202 Accepted. The job will be picked up by the next ingestion cycle.
    """
    stmt = (
        update(IngestionState)
        .where(
            IngestionState.id == job_id,
            IngestionState.current_stage == "FAILED",
        )
        .values(
            current_stage="DISCOVERED",
            error_message=None,
            stages_completed=[],
        )
        .returning(IngestionState.id)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        raise NotFoundError(
            error_code="JOB_NOT_FOUND",
            message="Job not found or not in FAILED state.",
        )

    await db.commit()
    logger.info("job_retried", job_id=str(job_id), admin_user_id=str(admin.id))

    return {"status": "retry_queued", "job_id": str(job_id)}


@router.post("/jobs/retry-all-failed", status_code=202)
async def retry_all_failed(
    admin: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset ALL FAILED jobs to DISCOVERED for re-processing.

    Returns 202 with the count of jobs reset.
    """
    stmt = (
        update(IngestionState)
        .where(IngestionState.current_stage == "FAILED")
        .values(
            current_stage="DISCOVERED",
            error_message=None,
            stages_completed=[],
        )
    )
    result = await db.execute(stmt)
    count = result.rowcount

    await db.commit()
    logger.info(
        "all_failed_jobs_retried",
        count=count,
        admin_user_id=str(admin.id),
    )

    return {"status": "retry_queued", "count": count}
