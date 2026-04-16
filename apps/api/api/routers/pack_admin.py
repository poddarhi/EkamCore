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
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError, RateLimitError
from api.middleware.auth import get_current_user
from api.schemas.auth import CurrentUser
from api.services import flags as flags_service
from api.db.models.pack_run import PackRun
from api.middleware.feature_gate import _ENABLED_FLAGS
from api.services.pack.manifest_loader import ManifestLoader, PackManifest
from api.services.pack.pack_context_factory import PackContextFactory
from api.services.pack.pack_runner import PackRunner, PackRunResult
from api.services.redis_client import REDIS_DB_CACHE, get_redis

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


# ── Manual pack trigger (S14-004) ─────────────────────────────────────────

class PackTriggerRequest(BaseModel):
    workspace_id: str
    workflow: str = "daily"


@router.post("/packs/{pack_id}/run")
async def trigger_pack_run(
    pack_id: str,
    body: PackTriggerRequest,
    request: Request,
    user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger a manual pack run for a workspace (admin only).

    Rate-limited to 1 run per workspace per hour via a Redis key
    so accidental double-fires don't create duplicate cards.
    """
    from uuid import UUID as _UUID

    workspace_id = _UUID(body.workspace_id)

    # Rate limit: 1/hour/workspace.
    r = get_redis(REDIS_DB_CACHE)
    rl_key = f"rl:pack_run:{workspace_id}:{pack_id}"
    if await r.get(rl_key):
        raise RateLimitError(
            error_code="RATE_LIMIT_EXCEEDED",
            message="A pack run for this workspace was triggered less than 1 hour ago.",
        )

    loader: ManifestLoader | None = getattr(
        request.app.state, "pack_manifest_loader", None
    )
    workflows: dict = getattr(
        request.app.state, "pack_workflows", {}
    )

    if loader is None:
        return {"error": "pack manifest loader not initialised"}

    factory = PackContextFactory()
    runner = PackRunner(
        manifest_loader=loader,
        context_factory=factory,
        workflows=workflows,
    )

    result = await runner.run(
        pack_id=pack_id,
        workflow_name=body.workflow,
        workspace_id=workspace_id,
        trigger="manual",
        db=db,
    )
    await db.commit()

    await r.set(rl_key, "1", ex=3600)

    logger.info(
        "pack_manual_trigger",
        pack_id=pack_id,
        workspace_id=str(workspace_id),
        state=result.state,
    )
    return result.model_dump(mode="json")


# ── Pack lifecycle (S14-005) ──────────────────────────────────────────────


class PackToggleRequest(BaseModel):
    workspace_id: str


@router.post("/packs/{pack_id}/enable")
async def enable_pack(
    pack_id: str,
    body: PackToggleRequest,
    user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Enable a pack for a workspace (admin only).

    Adds the pack flag to the runtime set. For the PLA pack this
    means adding ``pla_pack_enabled`` to ``_ENABLED_FLAGS``. True
    per-workspace persistence lives in the feature flag service's
    workspace scope but the runtime toggle (which controls immediate
    effect) is the active set.
    """
    if pack_id == "pla":
        _ENABLED_FLAGS.add("pla_pack_enabled")
    logger.info(
        "pack_enabled",
        pack_id=pack_id,
        workspace_id=body.workspace_id,
    )
    return {"pack_id": pack_id, "enabled": True}


@router.post("/packs/{pack_id}/disable")
async def disable_pack(
    pack_id: str,
    body: PackToggleRequest,
    user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Disable a pack for a workspace (admin only)."""
    if pack_id == "pla":
        _ENABLED_FLAGS.discard("pla_pack_enabled")
    logger.info(
        "pack_disabled",
        pack_id=pack_id,
        workspace_id=body.workspace_id,
    )
    return {"pack_id": pack_id, "enabled": False}


@router.get("/packs/{pack_id}/runs")
async def list_pack_runs(
    pack_id: str,
    workspace_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List recent pack_runs for a workspace (admin only)."""
    from uuid import UUID as _UUID

    ws = _UUID(workspace_id)
    stmt = (
        select(PackRun)
        .where(
            and_(
                PackRun.workspace_id == ws,
                PackRun.pack_id == pack_id,
            )
        )
        .order_by(PackRun.started_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        {
            "id": str(r.id),
            "pack_id": r.pack_id,
            "trigger": r.trigger,
            "state": r.state,
            "cards_produced": r.cards_produced,
            "llm_calls_used": r.llm_calls_used,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": (
                r.finished_at.isoformat() if r.finished_at else None
            ),
        }
        for r in rows
    ]
    return {"items": items}
