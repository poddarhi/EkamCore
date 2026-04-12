"""User-initiated face backfill service (S11-007).

Owns the lifecycle of ``face_backfill_jobs`` rows and the background
worker that walks a workspace's historical photos, invoking
``process_photo_for_faces`` on each.

Design principles (each one prevents a concrete bug class):

  1. **Consent is re-checked every batch.** The worker may run for
     minutes; the user may revoke in the middle. Before every batch
     boundary we re-check ``face_pipeline_active`` and honor revocation
     by marking the job ``cancelled``. ``ConsentService.revoke`` is
     what hard-deletes any face rows written by earlier batches, so
     the job body does not need its own cleanup — it just stops.

  2. **Cancellation flag lives in Redis**, keyed by workspace, so the
     worker task and the HTTP handler thread are decoupled and the
     cancel endpoint can act instantly without waiting for the worker
     to pick up a DB update.

  3. **Only one running job per workspace.** ``start_backfill`` refuses
     when a ``state='running'`` row exists — returns 409 via a typed
     exception so the API layer can map it cleanly.

  4. **Fresh DB session per worker run.** The worker runs via
     ``asyncio.create_task`` detached from the request, so it opens
     its own ``async_session()`` context. Each batch commits its own
     transaction so a mid-worker crash leaves the job row in a
     coherent "in-progress" state visible to the poller.

  5. **Photos to process are identified by ``face_processed_at IS NULL``.**
     This marker is stamped by ``face_ingestion.process_photo_for_faces``
     on every successful run (including zero-face), and cleared by
     ``hard_delete.delete_all_face_data`` on consent revocation — so
     backfill always has a truthful "never processed" set, independent
     of the old ``face_count=0`` ambiguity.

PII-safe logging (ART-14 §4): counts, ids, durations only. Never
bbox coords, never embeddings, never filenames.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_backfill_job import FaceBackfillJob
from api.db.models.photo_asset import PhotoAsset
from api.db.session import async_session
from api.errors import ConflictError, NotFoundError
from api.services.face.face_ingestion import process_photo_for_faces
from api.services.flags import face_pipeline_active
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

# Tunable constants — kept small because each photo runs under the
# P4 slot and touches Qdrant.
BATCH_SIZE = 50
CANCEL_KEY_PREFIX = "face_backfill:cancel:"
# TTL is longer than the longest plausible backfill (~hours) so stray
# cancel signals don't linger forever.
CANCEL_KEY_TTL_SECS = 6 * 60 * 60  # 6 hours


# ── Cancellation flag helpers (Redis) ──────────────────────────────────────


def _cancel_key(workspace_id: UUID) -> str:
    return f"{CANCEL_KEY_PREFIX}{workspace_id}"


async def _set_cancel_flag(workspace_id: UUID) -> None:
    r = get_redis(REDIS_DB_CACHE)
    await r.setex(_cancel_key(workspace_id), CANCEL_KEY_TTL_SECS, "1")


async def _clear_cancel_flag(workspace_id: UUID) -> None:
    r = get_redis(REDIS_DB_CACHE)
    await r.delete(_cancel_key(workspace_id))


async def _is_cancelled(workspace_id: UUID) -> bool:
    r = get_redis(REDIS_DB_CACHE)
    return await r.get(_cancel_key(workspace_id)) is not None


# ── Public service API (called by the router) ─────────────────────────────


async def _count_unprocessed(
    workspace_id: UUID, db: AsyncSession
) -> int:
    """Count photos in this workspace that have not yet been face-processed."""
    result = await db.execute(
        select(func.count(PhotoAsset.id)).where(
            and_(
                PhotoAsset.workspace_id == workspace_id,
                PhotoAsset.face_processed_at.is_(None),
                PhotoAsset.deleted_at.is_(None),
            )
        )
    )
    return int(result.scalar_one())


async def _get_running_job(
    workspace_id: UUID, db: AsyncSession
) -> FaceBackfillJob | None:
    result = await db.execute(
        select(FaceBackfillJob)
        .where(
            and_(
                FaceBackfillJob.workspace_id == workspace_id,
                FaceBackfillJob.state == "running",
            )
        )
        .order_by(desc(FaceBackfillJob.started_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_latest_job(
    workspace_id: UUID, db: AsyncSession
) -> FaceBackfillJob | None:
    """Return the most recent job for this workspace (any state), or None."""
    result = await db.execute(
        select(FaceBackfillJob)
        .where(FaceBackfillJob.workspace_id == workspace_id)
        .order_by(desc(FaceBackfillJob.started_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_backfill(
    workspace_id: UUID,
    db: AsyncSession,
    *,
    worker_factory: Any = None,
) -> FaceBackfillJob:
    """Create a face_backfill_jobs row and spawn the background worker.

    Refuses (409) when a ``running`` job already exists for this
    workspace. Consent is NOT re-checked here — the caller uses the
    standard ``require_face_consent`` dependency which performs that
    check in the request path.

    Args:
        workspace_id: Workspace to process.
        db: Caller's session. This function flushes but does not commit —
            the router commits so the job row is visible before we
            return.
        worker_factory: Optional override (tests). Callable of no
            arguments that returns the coroutine the background task
            will run. Defaults to the real worker closure.

    Returns:
        The newly inserted FaceBackfillJob row.

    Raises:
        ConflictError(BACKFILL_ALREADY_RUNNING): another job is running.
    """
    existing = await _get_running_job(workspace_id, db)
    if existing is not None:
        raise ConflictError(
            error_code="BACKFILL_ALREADY_RUNNING",
            message=(
                "A face backfill is already in progress for this workspace."
            ),
        )

    total = await _count_unprocessed(workspace_id, db)

    job = FaceBackfillJob(
        workspace_id=workspace_id,
        total_photos=total,
        processed_photos=0,
        failed_photos=0,
        state="running",
    )
    db.add(job)
    await db.flush()
    job_id = job.id

    # Make sure any stale cancel flag from a prior run doesn't
    # pre-cancel this one.
    await _clear_cancel_flag(workspace_id)

    # Spawn the background task. We intentionally do not await it — the
    # router returns the job row immediately and the UI polls for
    # progress.
    if worker_factory is None:
        coro = _run_backfill_worker(workspace_id, job_id)
    else:
        coro = worker_factory()
    asyncio.create_task(coro)

    logger.info(
        "face_backfill_started",
        workspace_id=str(workspace_id),
        job_id=str(job_id),
        total_photos=total,
    )
    return job


async def cancel_backfill(
    workspace_id: UUID, db: AsyncSession
) -> FaceBackfillJob:
    """Request cancellation of the running job for this workspace.

    Sets the Redis cancel flag AND updates the job row to ``cancelled``
    so the UI sees the state transition on its next poll without
    waiting for the worker to notice the flag. The worker will also
    notice the flag and stop at the next batch boundary.

    Raises:
        NotFoundError(BACKFILL_NOT_RUNNING): no active job to cancel.
    """
    running = await _get_running_job(workspace_id, db)
    if running is None:
        raise NotFoundError(
            error_code="BACKFILL_NOT_RUNNING",
            message="No face backfill is running for this workspace.",
        )

    await _set_cancel_flag(workspace_id)
    running.state = "cancelled"
    running.finished_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "face_backfill_cancel_requested",
        workspace_id=str(workspace_id),
        job_id=str(running.id),
    )
    return running


# ── Background worker ─────────────────────────────────────────────────────


async def _load_unprocessed_batch(
    workspace_id: UUID,
    db: AsyncSession,
    limit: int,
) -> list[UUID]:
    """Return up to `limit` photo_asset ids needing face processing."""
    result = await db.execute(
        select(PhotoAsset.id)
        .where(
            and_(
                PhotoAsset.workspace_id == workspace_id,
                PhotoAsset.face_processed_at.is_(None),
                PhotoAsset.deleted_at.is_(None),
            )
        )
        .order_by(PhotoAsset.id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _run_backfill_worker(
    workspace_id: UUID, job_id: UUID
) -> None:
    """Background task entry point. Never raises — errors are captured
    into the job row so the UI poller sees a coherent terminal state.
    """
    try:
        async with async_session() as db:
            await _process_workspace(workspace_id, job_id, db)
    except Exception:
        logger.error(
            "face_backfill_worker_unhandled",
            workspace_id=str(workspace_id),
            job_id=str(job_id),
            exc_info=True,
        )
        # Best-effort: open a fresh session and mark the row failed
        try:
            async with async_session() as db:
                await _mark_job_terminal(
                    db, job_id, state="failed", error="worker crashed"
                )
                await db.commit()
        except Exception:
            logger.error(
                "face_backfill_worker_terminal_update_failed",
                workspace_id=str(workspace_id),
                job_id=str(job_id),
                exc_info=True,
            )


async def _mark_job_terminal(
    db: AsyncSession,
    job_id: UUID,
    *,
    state: str,
    error: str | None = None,
) -> None:
    """Set a job row to a terminal state. Idempotent: if the row is
    already terminal we leave it alone so cancellation and natural
    completion don't race to overwrite each other."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(FaceBackfillJob)
        .where(
            and_(
                FaceBackfillJob.id == job_id,
                FaceBackfillJob.state == "running",
            )
        )
        .values(state=state, finished_at=now, error_message=error)
    )


async def _process_workspace(
    workspace_id: UUID, job_id: UUID, db: AsyncSession
) -> None:
    """Iterate photos in batches, processing each one."""
    processed = 0
    failed = 0

    while True:
        # 1. Cancel check (cheap Redis read)
        if await _is_cancelled(workspace_id):
            logger.info(
                "face_backfill_cancelled_by_flag",
                workspace_id=str(workspace_id),
                job_id=str(job_id),
                processed=processed,
            )
            await _mark_job_terminal(db, job_id, state="cancelled")
            await db.commit()
            await _clear_cancel_flag(workspace_id)
            return

        # 2. Consent re-check — revocation should stop the worker even
        #    if the cancel flag hasn't been set (revoke doesn't set it
        #    directly; hard_delete runs inline with revoke and wipes
        #    anything we've already written, so we just need to stop).
        if not await face_pipeline_active(workspace_id, db):
            logger.info(
                "face_backfill_cancelled_consent_revoked",
                workspace_id=str(workspace_id),
                job_id=str(job_id),
                processed=processed,
            )
            await _mark_job_terminal(db, job_id, state="cancelled")
            await db.commit()
            return

        # 3. Load next batch
        photo_ids = await _load_unprocessed_batch(
            workspace_id, db, BATCH_SIZE
        )
        if not photo_ids:
            break

        # 4. Process each photo. Exceptions from one photo must not
        #    poison the batch — we record the failure and keep going.
        for pid in photo_ids:
            try:
                await process_photo_for_faces(pid, db)
                processed += 1
            except Exception:
                failed += 1
                logger.warning(
                    "face_backfill_photo_failed",
                    workspace_id=str(workspace_id),
                    job_id=str(job_id),
                    photo_asset_id=str(pid),
                    exc_info=True,
                )

        # 5. Commit batch-worth of work + progress update
        await db.execute(
            update(FaceBackfillJob)
            .where(
                and_(
                    FaceBackfillJob.id == job_id,
                    FaceBackfillJob.state == "running",
                )
            )
            .values(
                processed_photos=processed,
                failed_photos=failed,
            )
        )
        await db.commit()

    # Natural completion
    await _mark_job_terminal(db, job_id, state="completed")
    await db.execute(
        update(FaceBackfillJob)
        .where(FaceBackfillJob.id == job_id)
        .values(processed_photos=processed, failed_photos=failed)
    )
    await db.commit()
    logger.info(
        "face_backfill_completed",
        workspace_id=str(workspace_id),
        job_id=str(job_id),
        processed=processed,
        failed=failed,
    )
