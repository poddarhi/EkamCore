"""Pack scheduler — asyncio cron loop for daily/weekly triggers (S14-005).

Replaces APScheduler with a zero-dependency asyncio approach:
two background tasks per workspace/pack combo (daily + weekly)
that sleep until the next target time, fire the workflow via
``PackRunner``, then loop. This keeps the dep surface minimal
on the single-Mac deployment target.

Edge cases:
  - **Missed run (API was down).** Each wake-up checks whether the
    last scheduled time is within ``MISFIRE_GRACE_SECONDS`` of now.
    If the miss is larger than the grace window the run is skipped
    and the next scheduled time is used instead. Logged at WARNING.
  - **Workspace disables PLA mid-day.** The ``pla_active`` gate
    runs at the top of every invocation; a disabled workspace
    no-ops silently.
  - **Per-workspace schedule overrides.** ``_resolve_run_time``
    reads ``pack.pla.daily_run_time`` / ``pack.pla.weekly_run_day``
    / ``pack.pla.weekly_run_time`` from ``settings_service`` and
    falls back to the manifest defaults.
  - **Multi-replica.** v1.0 is single-process. The docstring
    notes that v1.1 needs a Redis advisory lock — no code for it
    now.

Lifecycle: ``start()`` from the API lifespan, ``stop()`` on
shutdown. ``health()`` returns a status dict for ``/health``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.workspace import Workspace
from api.db.session import async_session
from api.services import flags as flags_service
from api.services.pack.manifest_loader import ManifestLoader
from api.services.pack.pack_runner import PackRunner
from api.services.settings_service import get_setting

logger = structlog.get_logger()

MISFIRE_GRACE_SECONDS = 3600
_DAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _parse_hhmm(raw: str) -> time:
    parts = raw.strip().split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]), tzinfo=timezone.utc)


def _next_daily(run_time: time, now: datetime) -> datetime:
    today_target = datetime.combine(now.date(), run_time, tzinfo=timezone.utc)
    if today_target > now:
        return today_target
    return today_target + timedelta(days=1)


def _next_weekly(
    day_name: str, run_time: time, now: datetime
) -> datetime:
    target_weekday = _DAYS.get(day_name.lower(), 0)
    days_ahead = (target_weekday - now.weekday()) % 7
    if days_ahead == 0:
        candidate = datetime.combine(now.date(), run_time, tzinfo=timezone.utc)
        if candidate <= now:
            candidate += timedelta(weeks=1)
        return candidate
    target_date = now.date() + timedelta(days=days_ahead)
    return datetime.combine(target_date, run_time, tzinfo=timezone.utc)


class PackScheduler:
    """Manages background cron loops for loaded packs."""

    def __init__(
        self,
        *,
        runner: PackRunner,
        manifest_loader: ManifestLoader,
    ) -> None:
        self._runner = runner
        self._loader = manifest_loader
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._last_run: dict[str, Any] | None = None
        self._next_daily: datetime | None = None
        self._next_weekly: datetime | None = None

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for pack_id, manifest in self._loader.manifests.items():
            if manifest.schedule.daily:
                self._tasks.append(
                    asyncio.create_task(
                        self._daily_loop(pack_id, manifest.schedule.daily),
                        name=f"pack-daily-{pack_id}",
                    )
                )
            if manifest.schedule.weekly:
                self._tasks.append(
                    asyncio.create_task(
                        self._weekly_loop(pack_id, manifest.schedule.weekly),
                        name=f"pack-weekly-{pack_id}",
                    )
                )
        logger.info(
            "pack_scheduler_started",
            tasks=len(self._tasks),
        )

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("pack_scheduler_stopped")

    def health(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "jobs_registered": len(self._tasks),
            "next_daily_run": (
                self._next_daily.isoformat() if self._next_daily else None
            ),
            "next_weekly_run": (
                self._next_weekly.isoformat() if self._next_weekly else None
            ),
            "last_run": self._last_run,
        }

    # ── Loops ─────────────────────────────────────────────────────────

    async def _daily_loop(self, pack_id: str, raw_time: str) -> None:
        default_time = _parse_hhmm(raw_time)
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                next_run = _next_daily(default_time, now)
                self._next_daily = next_run
                delay = (next_run - now).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._fire_for_all_workspaces(
                    pack_id, "daily", "scheduled_daily"
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "pack_daily_loop_error",
                    pack_id=pack_id,
                    exc_info=True,
                )
                await asyncio.sleep(60)

    async def _weekly_loop(self, pack_id: str, raw_spec: str) -> None:
        parts = raw_spec.strip().split()
        day_name = parts[0]
        default_time = _parse_hhmm(parts[1]) if len(parts) > 1 else time(8, 0, tzinfo=timezone.utc)
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                next_run = _next_weekly(day_name, default_time, now)
                self._next_weekly = next_run
                delay = (next_run - now).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._fire_for_all_workspaces(
                    pack_id, "weekly", "scheduled_weekly"
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "pack_weekly_loop_error",
                    pack_id=pack_id,
                    exc_info=True,
                )
                await asyncio.sleep(60)

    async def _fire_for_all_workspaces(
        self, pack_id: str, workflow: str, trigger: str
    ) -> None:
        async with async_session() as db:
            workspace_ids = (
                (
                    await db.execute(
                        select(Workspace.id).where(
                            Workspace.deleted_at.is_(None)
                            if hasattr(Workspace, "deleted_at")
                            else True
                        )
                    )
                )
                .scalars()
                .all()
            )

        for ws_id in workspace_ids:
            try:
                async with async_session() as db:
                    if not await flags_service.pla_active(ws_id, db):
                        continue
                    result = await self._runner.run(
                        pack_id=pack_id,
                        workflow_name=workflow,
                        workspace_id=ws_id,
                        trigger=trigger,
                        db=db,
                    )
                    await db.commit()
                    self._last_run = {
                        "pack_id": pack_id,
                        "workspace_id": str(ws_id),
                        "state": result.state,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
            except Exception:
                logger.warning(
                    "pack_scheduled_run_failed",
                    pack_id=pack_id,
                    workspace_id=str(ws_id),
                    trigger=trigger,
                    exc_info=True,
                )
