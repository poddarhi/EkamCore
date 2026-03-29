"""Source registration and management service."""

import base64
import structlog
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.source import Source
from api.errors import ConflictError, NotFoundError, ValidationError
from api.schemas.source import SourceCreate, SourceUpdate, _FOLDER_TYPES

logger = structlog.get_logger()

_DEFAULT_PAGE_SIZE = 20


def _encode_cursor(source_id: UUID) -> str:
    return base64.urlsafe_b64encode(str(source_id).encode()).decode()


def _decode_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


async def list_sources(
    workspace_ids: list[UUID],
    db: AsyncSession,
    cursor: str | None = None,
    limit: int = _DEFAULT_PAGE_SIZE,
) -> tuple[list[Source], str | None]:
    """Return a page of active sources for the given workspaces.

    Returns (items, next_cursor). next_cursor is None when there are no more pages.
    """
    stmt = (
        select(Source)
        .where(
            Source.workspace_id.in_(workspace_ids),
            Source.deleted_at.is_(None),
        )
        .order_by(Source.id)
    )

    if cursor:
        after_id = _decode_cursor(cursor)
        stmt = stmt.where(Source.id > after_id)

    stmt = stmt.limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].id)
    else:
        next_cursor = None

    return rows, next_cursor


async def create_source(
    workspace_id: UUID,
    registered_by: UUID,
    body: SourceCreate,
    db: AsyncSession,
) -> Source:
    """Register a new source. Raises ConflictError on duplicate, ValidationError if path missing/absent."""
    if body.type in _FOLDER_TYPES:
        if not body.path:
            raise ValidationError(
                error_code="SOURCE_PATH_REQUIRED",
                message=f"path is required for source type '{body.type}'.",
            )
        if not Path(body.path).exists():
            raise ValidationError(
                error_code="SOURCE_PATH_NOT_FOUND",
                message=f"Path does not exist: {body.path}",
            )

    # Duplicate check: UNIQUE(workspace_id, type, path)
    dup_stmt = select(Source).where(
        Source.workspace_id == workspace_id,
        Source.type == body.type,
        Source.path == body.path,
        Source.deleted_at.is_(None),
    )
    existing = (await db.execute(dup_stmt)).scalar_one_or_none()
    if existing:
        raise ConflictError(
            error_code="SOURCE_DUPLICATE",
            message="A source with this type and path already exists in this workspace.",
        )

    source = Source(
        workspace_id=workspace_id,
        registered_by=registered_by,
        name=body.name,
        type=body.type,
        path=body.path,
        config_json=body.config_json,
        status="active",
    )
    db.add(source)
    await db.flush()

    logger.info("source_registered", source_id=str(source.id), source_type=body.type, workspace_id=str(workspace_id))
    # TODO(S03-008): enqueue initial ingestion scan via ARQ worker
    return source


async def update_source(
    source_id: UUID,
    workspace_ids: list[UUID],
    body: SourceUpdate,
    db: AsyncSession,
) -> Source:
    """Update name, status, or config_json. Raises NotFoundError if not found."""
    source = await _get_owned(source_id, workspace_ids, db)

    if body.name is not None:
        source.name = body.name
    if body.status is not None:
        source.status = body.status
    if body.config_json is not None:
        source.config_json = body.config_json

    await db.flush()
    return source


async def delete_source(
    source_id: UUID,
    workspace_ids: list[UUID],
    db: AsyncSession,
) -> None:
    """Soft-delete a source. Data retained for 30 days per policy."""
    from datetime import datetime, timezone

    source = await _get_owned(source_id, workspace_ids, db)
    source.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info("source_soft_deleted", source_id=str(source_id))


async def _get_owned(source_id: UUID, workspace_ids: list[UUID], db: AsyncSession) -> Source:
    stmt = select(Source).where(
        Source.id == source_id,
        Source.workspace_id.in_(workspace_ids),
        Source.deleted_at.is_(None),
    )
    source = (await db.execute(stmt)).scalar_one_or_none()
    if not source:
        raise NotFoundError(error_code="SOURCE_NOT_FOUND", message="Source not found.")
    return source
