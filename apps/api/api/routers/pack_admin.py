"""Pack admin router (S14-002).

Exposes ``GET /api/v1/admin/packs`` so ops can confirm which packs
the loader picked up at startup and whether each is enabled for
the caller's workspace. Requires an admin JWT like the other
``/api/v1/admin`` endpoints, but does NOT gate on the
``audit_log_enabled`` flag — pack inspection should work even when
audit export is off for maintenance.

Enabled state is derived from ``flags.pla_active`` for PLA and
from the PLA flag alone for any future non-consent pack. The
result set is stable: missing manifests are reported via the
``load_errors`` array so an ops page can explain "why is PLA
missing?" without grepping logs.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.schemas.auth import CurrentUser
from api.services import flags as flags_service
from api.services.pack.manifest_loader import ManifestLoader, PackManifest

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin-packs"])


def _require_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if user.role != "admin":
        raise AuthorizationError(
            error_code="ADMIN_REQUIRED",
            message="Admin role required for this endpoint.",
        )
    return user


def _manifest_to_dict(
    manifest: PackManifest, *, enabled: bool
) -> dict[str, Any]:
    return {
        "pack_id": manifest.pack_id,
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "capabilities": list(manifest.capabilities),
        "card_types": list(manifest.card_types),
        "schedule": {
            "daily": manifest.schedule.daily,
            "weekly": manifest.schedule.weekly,
        },
        "resource_limits": {
            "max_execution_time_seconds": manifest.resource_limits.max_execution_time_seconds,
            "max_memory_mb": manifest.resource_limits.max_memory_mb,
            "max_llm_calls_per_run": manifest.resource_limits.max_llm_calls_per_run,
        },
        "enabled": enabled,
    }


async def _pack_enabled(
    pack_id: str, workspace_id, db: AsyncSession
) -> bool:
    """Per-pack feature gate. PLA uses the full three-way check;
    any future pack defaults to ``pla_pack_enabled`` semantics
    until it gets its own gate."""
    if pack_id == "pla":
        return await flags_service.pla_active(workspace_id, db)
    # Conservative default: unknown pack_id → not enabled.
    return False


@router.get("/packs")
async def list_packs(
    request: Request,
    user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return every loaded pack with its metadata + enabled state
    for the caller's workspace.

    Packs that failed validation at startup surface via the
    ``load_errors`` array (``[{path, error}, ...]``) so the UI
    can explain missing packs without a log dive.
    """
    loader: ManifestLoader | None = getattr(
        request.app.state, "pack_manifest_loader", None
    )
    if loader is None:
        return {"packs": [], "load_errors": []}

    workspace_id = user.workspace_ids[0] if user.workspace_ids else None

    packs_payload: list[dict[str, Any]] = []
    for manifest in loader.manifests.values():
        enabled = False
        if workspace_id is not None:
            try:
                enabled = await _pack_enabled(
                    manifest.pack_id, workspace_id, db
                )
            except Exception:
                logger.warning(
                    "pack_admin_enabled_check_failed",
                    pack_id=manifest.pack_id,
                    exc_info=True,
                )
                enabled = False
        packs_payload.append(_manifest_to_dict(manifest, enabled=enabled))

    return {"packs": packs_payload, "load_errors": loader.load_errors}
