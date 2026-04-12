"""Hard deletion of face pipeline data (S11-003 implementation).

Thin adapter that delegates to api.services.face.hard_delete.delete_all_face_data.

Why this indirection? S11-002 established `data_erasure.hard_delete_all_face_data`
as the contract surface that ConsentService.revoke() calls and that tests
monkeypatch for failure injection. S11-003 ships the real implementation
in a separate `hard_delete.py` module so the logic can be unit-tested
directly without going through ConsentService. This module preserves the
contract signature and forwards to the real implementation, so S11-002
tests that monkeypatch `data_erasure.hard_delete_all_face_data` continue
to work unchanged.

ART-15 §3 row 3: "Right to delete — Synchronous, verified". The real
implementation deletes Qdrant points FIRST (irreplaceable ciphertext),
verifies Qdrant is empty, then cascades to PG metadata in a single
transaction. See hard_delete.py for the full failure-mode analysis.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.face.hard_delete import (
    DeleteReport,
    delete_all_face_data,
)

logger = structlog.get_logger()


async def hard_delete_all_face_data(
    workspace_id: UUID,
    db: AsyncSession,
) -> DeleteReport:
    """Erase all face pipeline data for a workspace.

    Forwards to :func:`api.services.face.hard_delete.delete_all_face_data`.

    Args:
        workspace_id: The workspace whose face data should be erased.
        db: Async session used for the atomic PG cascade.

    Returns:
        DeleteReport with deletion counts and duration.

    Raises:
        ServiceUnavailableError with error_code starting in
        FACE_HARD_DELETE_ on any failure. The caller MUST roll back.
    """
    return await delete_all_face_data(
        workspace_id=workspace_id,
        db=db,
    )
