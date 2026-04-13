"""Helper for recording person_operations rows (S12-006).

Each forward operation (merge, split, rename, delete) calls
``record()`` inside its own transaction. The caller is responsible
for committing; this helper only ``flushes``.

Operations are not deduplicated — a sequence of renames produces
one row per rename. The undo service walks the log in descending
created_at order and only considers rows whose ``undone_at`` is
NULL.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.person_operation import PersonOperation


async def record(
    *,
    db: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    operation_type: str,
    forward_payload: dict[str, Any],
    inverse_payload: dict[str, Any],
) -> PersonOperation:
    row = PersonOperation(
        workspace_id=workspace_id,
        user_id=user_id,
        operation_type=operation_type,
        forward_payload=forward_payload,
        inverse_payload=inverse_payload,
    )
    db.add(row)
    await db.flush()
    return row
