"""Hard deletion of face pipeline data (S11-002 stub, S11-003 implementation).

This module is called by ConsentService.revoke() to erase all face data
for a workspace BEFORE the revocation is committed. If hard_delete raises,
revocation is rolled back (partial state is forbidden by ART-15 §3).

STATUS: STUB. S11-002 provides a callable no-op so the ConsentService can
be implemented and tested end-to-end. S11-003 replaces the body of
`hard_delete_all_face_data` with the real cascade:
    - DELETE FROM face_detections WHERE workspace_id = :ws
    - DELETE FROM face_clusters   WHERE workspace_id = :ws
    - Qdrant scroll + delete all face_embedding points where
      workspace_id = :ws
    - Emit a terminal audit_log row recording the erasure

Tests that want to simulate a failed erasure (to verify the rollback
contract) MUST monkeypatch this function — not its internals — so the
contract surface is stable across S11-002 and S11-003.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def hard_delete_all_face_data(
    workspace_id: UUID,
    db: AsyncSession,
) -> None:
    """Erase all face pipeline data for a workspace.

    STUB: S11-003 implements the actual DELETE + Qdrant scroll cascade.
    For S11-002, this is a no-op that logs a structured warning so that
    accidental reliance on it in production is loud.

    Args:
        workspace_id: The workspace whose face data should be erased.
        db: Async session — S11-003 will use this to run the cascading
            deletes atomically with the caller's transaction.

    Raises:
        Any exception raised by this function propagates to the caller,
        which MUST roll back its transaction. ConsentService.revoke()
        relies on this contract.
    """
    logger.warning(
        "face_data_erasure_stub_invoked",
        workspace_id=str(workspace_id),
        message=(
            "hard_delete_all_face_data is a STUB (S11-002). "
            "S11-003 will implement actual deletion. "
            "No face data has been erased."
        ),
    )
    # Intentionally a no-op until S11-003 lands.
    return None
