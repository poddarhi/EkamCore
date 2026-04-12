"""Ingestion pipeline state machine with optimistic concurrency.

Transition rule: UPDATE ingestion_states SET current_stage=:new
WHERE file_id=:fid AND current_stage=:expected.
If 0 rows affected → already advanced (idempotent, not an error).
Per-file error isolation: one file's failure never blocks another.
"""

from uuid import UUID

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.ingestion_state import IngestionState

logger = structlog.get_logger()

# Ordered pipeline stages (happy path)
PIPELINE_STAGES: list[str] = [
    "DISCOVERED",
    "FINGERPRINTED",
    "METADATA_EXTRACTED",
    # Photos only: consent-gated face detection (S11-006). For non-photo
    # files this stage is a no-op advance — there is no image to decode.
    "FACE_DETECTION",
    "TEXT_EXTRACTED",
    "OCR_COMPLETED",
    "EMBEDDING_QUEUED",
    "EMBEDDED",
    "COMPLETED",
]

# Terminal stages that cannot be transitioned from
TERMINAL_STAGES: set[str] = {"COMPLETED", "FAILED", "SKIPPED"}

# Map each stage to its next stage in the pipeline
_NEXT_STAGE: dict[str, str] = {
    PIPELINE_STAGES[i]: PIPELINE_STAGES[i + 1] for i in range(len(PIPELINE_STAGES) - 1)
}

MAX_RETRIES = 3


async def advance_stage(
    file_id: UUID,
    expected_stage: str,
    db: AsyncSession,
) -> bool:
    """Advance a file to the next pipeline stage using optimistic concurrency.

    Returns True if the transition succeeded, False if already advanced (idempotent).
    """
    if expected_stage in TERMINAL_STAGES:
        logger.warning(
            "advance_from_terminal_stage",
            file_id=str(file_id),
            stage=expected_stage,
        )
        return False

    next_stage = _NEXT_STAGE.get(expected_stage)
    if next_stage is None:
        logger.error(
            "unknown_pipeline_stage",
            file_id=str(file_id),
            stage=expected_stage,
        )
        return False

    stmt = (
        update(IngestionState)
        .where(
            IngestionState.file_id == file_id,
            IngestionState.current_stage == expected_stage,
        )
        .values(
            current_stage=next_stage,
            stages_completed=IngestionState.stages_completed + [expected_stage],
            error_message=None,
        )
    )
    result = await db.execute(stmt)

    advanced = result.rowcount > 0
    if advanced:
        logger.info(
            "stage_advanced",
            file_id=str(file_id),
            from_stage=expected_stage,
            to_stage=next_stage,
        )
    else:
        logger.info(
            "stage_already_advanced",
            file_id=str(file_id),
            expected_stage=expected_stage,
        )

    return advanced


async def fail_stage(
    file_id: UUID,
    expected_stage: str,
    error_message: str,
    db: AsyncSession,
) -> bool:
    """Mark a file as FAILED from the expected stage. Increments retry_count.

    Returns True if the transition succeeded, False if already transitioned.
    """
    stmt = (
        update(IngestionState)
        .where(
            IngestionState.file_id == file_id,
            IngestionState.current_stage == expected_stage,
            IngestionState.retry_count < MAX_RETRIES,
        )
        .values(
            current_stage="FAILED",
            error_message=error_message,
            retry_count=IngestionState.retry_count + 1,
        )
    )
    result = await db.execute(stmt)

    failed = result.rowcount > 0
    if failed:
        logger.warning(
            "stage_failed",
            file_id=str(file_id),
            stage=expected_stage,
            error=error_message,
        )

    return failed


async def skip_file(
    file_id: UUID,
    expected_stage: str,
    db: AsyncSession,
) -> bool:
    """Mark a file as SKIPPED from the expected stage.

    Returns True if the transition succeeded, False if already transitioned.
    """
    if expected_stage in TERMINAL_STAGES:
        return False

    stmt = (
        update(IngestionState)
        .where(
            IngestionState.file_id == file_id,
            IngestionState.current_stage == expected_stage,
        )
        .values(current_stage="SKIPPED")
    )
    result = await db.execute(stmt)

    skipped = result.rowcount > 0
    if skipped:
        logger.info(
            "file_skipped",
            file_id=str(file_id),
            from_stage=expected_stage,
        )

    return skipped
