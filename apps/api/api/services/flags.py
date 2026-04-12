"""Feature flag + consent service (S11-001 / ART-11).

Single source of truth for flag definitions and Phase 3 gate checks.

Two-layer model:
  1. **Flag registry** (this file) — declarative metadata for each flag:
     default state, scope, phase, description.

  2. **Active set** (api/middleware/feature_gate.py::_ENABLED_FLAGS) —
     runtime toggle. A flag in the active set is "ON" for everyone;
     absent means "OFF". Used by `require_flag()` dependencies.

For consent-gated flags like `face_clustering_enabled`, a FastAPI
`require_flag()` dependency is NOT sufficient because the runtime
state depends on both a flag AND a per-workspace consent record AND
the presence of an encryption key. Use `face_pipeline_active()` for
those three-way checks instead of chaining dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.middleware.feature_gate import _ENABLED_FLAGS

logger = structlog.get_logger()


@dataclass(frozen=True)
class FlagDef:
    """Declarative definition of a feature flag."""

    default: bool
    scope: Literal["workspace", "user", "global"]
    phase: int
    description: str


FLAG_REGISTRY: dict[str, FlagDef] = {
    "face_clustering_enabled": FlagDef(
        default=False,
        scope="workspace",
        phase=3,
        description=(
            "Enables face detection, embedding, clustering, and review "
            "queue. Requires explicit user consent and a configured "
            "FACE_EMBED_KEY."
        ),
    ),
    # Additional Phase 3+ flags can be registered here as they land.
}


def is_flag_enabled(flag_key: str) -> bool:
    """Check if a flag is currently in the runtime active set.

    Defined flags that are not yet activated return False. Unknown flags
    log a warning and also return False.
    """
    if flag_key not in FLAG_REGISTRY:
        logger.warning("flag_lookup_unknown_key", flag_key=flag_key)
        return False
    return flag_key in _ENABLED_FLAGS


async def face_pipeline_active(workspace_id: UUID, db: AsyncSession) -> bool:
    """Return True iff the face pipeline is fully operational for a workspace.

    Three conditions must ALL hold:
      1. `face_clustering_enabled` flag is in the runtime active set
      2. `FACE_EMBED_KEY` is configured (non-empty)
      3. An active face consent record exists for the workspace
         (see api.services.face.consent_service)

    All face endpoints and workers must call this — do not build a
    partial check elsewhere. One gate, one audit trail.

    The consent check is delegated to ConsentService, which is the sole
    reader/writer of consent state. S11-001 used a simple boolean in the
    core namespace; S11-002 replaced that with a rich JSONB record in
    the privacy namespace owned by ConsentService.

    Args:
        workspace_id: The workspace to check consent for.
        db: Async session for reading consent state.

    Returns:
        True if all three gates are satisfied, False otherwise.
    """
    # Gate 1: runtime flag
    if not is_flag_enabled("face_clustering_enabled"):
        return False

    # Gate 2: encryption key
    if not settings.FACE_EMBED_KEY:
        logger.warning(
            "face_pipeline_gate_key_missing",
            workspace_id=str(workspace_id),
        )
        return False

    # Gate 3: per-workspace consent, owned by ConsentService.
    # Import locally to avoid circular dependencies.
    from api.services.face import consent_service

    try:
        return await consent_service.is_consent_active(workspace_id, db)
    except Exception:
        logger.warning(
            "face_pipeline_gate_consent_read_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        return False
