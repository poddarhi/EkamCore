"""Pack sandbox runner (S14-004 / ART-13 §6 / ART-14).

``PackRunner.run`` is the single entry point that orchestrates a
complete pack execution:

    manifest lookup → context factory → DB row (running) →
    timeout-guarded workflow call → card commit → DB row (completed)

Sandbox enforcement layers (all applied within ``run``):

1. **Timeout.** ``asyncio.wait_for`` wraps the workflow callable.
   ``TimeoutError`` is caught, cards discarded, row stamped
   ``state='timeout'``.
2. **Memory (advisory).** RSS delta measured before/after via
   ``resource.getrusage``. Exceeding the manifest cap logs a
   WARNING but does not kill the run — hard enforcement requires
   process isolation (deferred to v1.1).
3. **Output sanitization.** Every card payload is already sanitized
   inside ``PackContext.produce_card``. The runner additionally
   rejects any single card whose JSON serialisation exceeds 64 KB.
4. **LLM quota.** Enforced inside ``PackContext.ask_llm`` — the
   runner reads ``context.llm_calls_used`` and persists it.
5. **Capability enforcement.** Structural: ``PackContext`` gates
   every read/write; the runner has no role here beyond assembling
   the context.

``PackWorkflowFn`` is the callable signature the runner expects.
The PLA pack (S14-005+) registers its workflows against this type.
"""

from __future__ import annotations

import asyncio
import json
import resource
import time
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.pack_card import PackCard
from api.db.models.pack_run import PackRun
from api.errors import (
    PackExecutionError,
    PackExecutionTimeoutError,
    PackNotFoundError,
)
from api.services import audit
from api.services.pack.manifest_loader import ManifestLoader
from api.services.pack.pack_context import PackContext
from api.services.pack.pack_context_factory import PackContextFactory

logger = structlog.get_logger()

#: Maximum JSON size of a single card payload. Cards larger than
#: this are silently dropped with a WARNING log.
MAX_CARD_PAYLOAD_BYTES = 64 * 1024

PackWorkflowFn = Callable[[PackContext], Awaitable[None]]


class PackRunResult(BaseModel):
    """Returned from ``PackRunner.run``. Serialisable so callers
    (the admin endpoint, the scheduler) can surface it directly."""

    pack_run_id: UUID
    state: str
    cards_produced: int
    llm_calls_used: int
    duration_ms: int
    error: str | None = None
    degraded_capabilities: list[str] = []


def _rss_mb() -> float:
    """Return the current-process RSS in megabytes."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS returns bytes, Linux returns KB — normalise.
    if hasattr(usage, "ru_maxrss"):
        # macOS: bytes
        import sys

        if sys.platform == "darwin":
            return usage.ru_maxrss / (1024 * 1024)
        return usage.ru_maxrss / 1024
    return 0.0


def _compute_target_date(trigger: str) -> date:
    """Derive the card ``target_date`` from the trigger name.

    - ``daily_*`` → today.
    - ``weekly_*`` → the Monday of the current ISO week.
    - Anything else → today (safe fallback).
    """
    today = datetime.now(timezone.utc).date()
    if trigger.startswith("weekly"):
        return today - __import__("datetime").timedelta(days=today.weekday())
    return today


class PackRunner:
    """Orchestrates a sandboxed pack execution.

    Stateless — one instance can serve every pack/workspace combo.
    Callers must pass a ``ManifestLoader`` (from ``app.state``),
    a ``PackContextFactory``, and a registry of workflow callables.
    """

    def __init__(
        self,
        *,
        manifest_loader: ManifestLoader,
        context_factory: PackContextFactory,
        workflows: dict[str, PackWorkflowFn],
    ) -> None:
        self._loader = manifest_loader
        self._factory = context_factory
        self._workflows = workflows

    async def run(
        self,
        *,
        pack_id: str,
        workflow_name: str,
        workspace_id: UUID,
        trigger: str,
        db: AsyncSession,
    ) -> PackRunResult:
        manifest = self._loader.get(pack_id)
        if manifest is None:
            raise PackNotFoundError(
                error_code="PACK_NOT_FOUND",
                message=f"No manifest loaded for pack '{pack_id}'.",
            )
        workflow_fn = self._workflows.get(workflow_name)
        if workflow_fn is None:
            raise PackNotFoundError(
                error_code="PACK_NOT_FOUND",
                message=f"No workflow '{workflow_name}' registered.",
            )

        run_row = PackRun(
            workspace_id=workspace_id,
            pack_id=pack_id,
            trigger=trigger,
            state="running",
        )
        db.add(run_row)
        await db.flush()
        run_id = run_row.id

        ctx = await self._factory.create(
            workspace_id=workspace_id,
            manifest=manifest,
            db=db,
            pack_run_id=run_id,
        )

        degraded: list[str] = sorted(
            set(manifest.capabilities) - set(ctx.capabilities)
        )

        rss_before = _rss_mb()
        t0 = time.monotonic()
        error_msg: str | None = None
        final_state = "completed"

        try:
            await asyncio.wait_for(
                workflow_fn(ctx),
                timeout=float(
                    manifest.resource_limits.max_execution_time_seconds
                ),
            )
        except asyncio.TimeoutError:
            final_state = "timeout"
            error_msg = (
                f"pack '{pack_id}' timed out after "
                f"{manifest.resource_limits.max_execution_time_seconds}s"
            )
            logger.warning(
                "pack_run_timeout",
                pack_id=pack_id,
                workspace_id=str(workspace_id),
            )
        except Exception as exc:
            final_state = "failed"
            error_msg = str(exc)[:2000]
            logger.warning(
                "pack_run_failed",
                pack_id=pack_id,
                workspace_id=str(workspace_id),
                exc_info=True,
            )

        duration_ms = int((time.monotonic() - t0) * 1000)
        rss_after = _rss_mb()
        rss_delta = rss_after - rss_before
        if rss_delta > manifest.resource_limits.max_memory_mb:
            logger.warning(
                "pack_run_memory_exceeded_advisory",
                pack_id=pack_id,
                workspace_id=str(workspace_id),
                rss_delta_mb=round(rss_delta, 1),
                limit_mb=manifest.resource_limits.max_memory_mb,
            )

        # Card commit — only if the run succeeded.
        cards_committed = 0
        if final_state == "completed":
            target_date = _compute_target_date(trigger)
            for card in ctx.cards:
                card_json = json.dumps(card["payload"], default=str)
                if len(card_json.encode()) > MAX_CARD_PAYLOAD_BYTES:
                    logger.warning(
                        "pack_card_payload_too_large",
                        pack_id=pack_id,
                        card_type=card["card_type"],
                        bytes=len(card_json.encode()),
                    )
                    continue
                db.add(
                    PackCard(
                        workspace_id=workspace_id,
                        pack_run_id=run_id,
                        card_type=card["card_type"],
                        payload_json=card["payload"],
                        target_date=target_date,
                    )
                )
                cards_committed += 1

        run_row.state = final_state
        run_row.cards_produced = cards_committed
        run_row.llm_calls_used = ctx.llm_calls_used
        run_row.duration_ms = duration_ms
        run_row.error_message = error_msg
        run_row.finished_at = datetime.now(timezone.utc)
        await db.flush()

        await audit.log_event(
            db=db,
            action="pack_run_completed",
            object_type="pack_runs",
            object_id=run_id,
            workspace_id=workspace_id,
            metadata={
                "pack_id": pack_id,
                "trigger": trigger,
                "state": final_state,
                "cards_produced": cards_committed,
                "llm_calls_used": ctx.llm_calls_used,
                "duration_ms": duration_ms,
                "degraded_capabilities": degraded,
            },
        )

        logger.info(
            "pack_run_complete",
            pack_id=pack_id,
            workspace_id=str(workspace_id),
            state=final_state,
            cards=cards_committed,
            llm_calls=ctx.llm_calls_used,
            duration_ms=duration_ms,
        )

        return PackRunResult(
            pack_run_id=run_id,
            state=final_state,
            cards_produced=cards_committed,
            llm_calls_used=ctx.llm_calls_used,
            duration_ms=duration_ms,
            error=error_msg,
            degraded_capabilities=degraded,
        )
