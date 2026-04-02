"""S04-001 — Resource Controller

Priority-based concurrency slot management with Redis-backed preempt signalling
and thermal awareness.

Priority levels (ascending = lower priority):
  P1 Interactive          – user query;     preempts P3/P4 within 500 ms
  P2 Pack Execution       – background AI
  P3 Background Important – embeddings, sync
  P4 Background Low       – face pipeline, clustering, maintenance

Semaphore slots:
  P1: 1   P2: 1   P3: 2   P4: 2

Redis keys (DB 3 — REDIS_DB_CACHE):
  rc:preempt       – set to "1" while a P1 slot is held; workers poll this
  rc:thermal_state – "nominal" | "fair" | "serious" | "critical"

Usage (service / worker):
    async with acquire_slot(Priority.P3_BACKGROUND_IMPORTANT):
        for item in batch:
            if await is_preempted():
                break          # defer; P1 is active
            await process(item)

    batch_size = await get_p4_batch_size(default=50)
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
from collections.abc import AsyncGenerator

import structlog

from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Redis key names
# ---------------------------------------------------------------------------

_KEY_PREEMPT = "rc:preempt"
_KEY_THERMAL = "rc:thermal_state"
_PREEMPT_TTL_SECS = 30  # safety TTL; cleared eagerly when P1 slot released


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Priority(enum.IntEnum):
    """Task priority.  Lower integer = higher priority (P1 > P2 > P3 > P4)."""

    P1_INTERACTIVE = 1
    P2_PACK = 2
    P3_BACKGROUND_IMPORTANT = 3
    P4_BACKGROUND_LOW = 4


class ThermalState(str, enum.Enum):
    """Thermal pressure level published by the Tauri manager app."""

    NOMINAL = "nominal"
    FAIR = "fair"
    SERIOUS = "serious"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Internal exception (not an HTTP error — service-layer only)
# ---------------------------------------------------------------------------


class ResourceThrottledError(Exception):
    """Raised when a slot cannot be acquired due to thermal pressure.

    Callers (workers) catch this and defer the task.
    """

    def __init__(self, *, priority: Priority, reason: str) -> None:
        self.priority = priority
        self.reason = reason
        super().__init__(f"Slot for {priority.name} throttled: {reason}")


# ---------------------------------------------------------------------------
# Slot configuration
# ---------------------------------------------------------------------------

_SLOT_COUNTS: dict[Priority, int] = {
    Priority.P1_INTERACTIVE: 1,
    Priority.P2_PACK: 1,
    Priority.P3_BACKGROUND_IMPORTANT: 2,
    Priority.P4_BACKGROUND_LOW: 2,
}

# Semaphores keyed by (event-loop-id, priority) so tests with separate loops
# each get fresh semaphores without leaking state between test cases.
_semaphores: dict[tuple[int, Priority], asyncio.BoundedSemaphore] = {}


def _get_semaphore(priority: Priority) -> asyncio.BoundedSemaphore:
    """Return (creating if necessary) the semaphore for *priority* on the
    current running event loop."""
    loop_id = id(asyncio.get_running_loop())
    key = (loop_id, priority)
    if key not in _semaphores:
        _semaphores[key] = asyncio.BoundedSemaphore(_SLOT_COUNTS[priority])
    return _semaphores[key]


# ---------------------------------------------------------------------------
# Preempt signal helpers
# ---------------------------------------------------------------------------


async def _signal_preempt() -> None:
    """Set the preempt key (with TTL) and publish to the pub/sub channel.

    P3/P4 workers check `is_preempted()` before each batch item.
    """
    r = get_redis(REDIS_DB_CACHE)
    await r.setex(_KEY_PREEMPT, _PREEMPT_TTL_SECS, "1")
    await r.publish(_KEY_PREEMPT, "preempt")
    logger.debug("rc_preempt_signalled")


async def _clear_preempt() -> None:
    """Delete the preempt key so P3/P4 workers may resume."""
    r = get_redis(REDIS_DB_CACHE)
    await r.delete(_KEY_PREEMPT)
    logger.debug("rc_preempt_cleared")


# ---------------------------------------------------------------------------
# Public API — slot acquisition
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def acquire_slot(priority: Priority) -> AsyncGenerator[None, None]:
    """Async context manager that acquires a concurrency slot for *priority*.

    Behaviour per priority:
    • P1: acquires immediately (1 slot), signals preempt on entry, clears on exit.
    • P2: acquires immediately (1 slot); no preempt signal.
    • P3/P4: checks thermal state first — raises ResourceThrottledError when
      state is CRITICAL; then waits for an available slot.

    Yields control once the slot is held; releases on exit regardless of
    exceptions.
    """
    # Pre-acquisition thermal gate for background work
    if priority in (Priority.P3_BACKGROUND_IMPORTANT, Priority.P4_BACKGROUND_LOW):
        thermal = await get_thermal_state()
        if thermal == ThermalState.CRITICAL:
            raise ResourceThrottledError(priority=priority, reason="thermal_critical")

    sem = _get_semaphore(priority)

    logger.debug("rc_slot_waiting", priority=priority.name)
    async with sem:
        logger.debug("rc_slot_acquired", priority=priority.name)
        if priority == Priority.P1_INTERACTIVE:
            await _signal_preempt()
        try:
            yield
        finally:
            if priority == Priority.P1_INTERACTIVE:
                await _clear_preempt()
            logger.debug("rc_slot_released", priority=priority.name)


# ---------------------------------------------------------------------------
# Public API — worker helpers
# ---------------------------------------------------------------------------


async def is_preempted() -> bool:
    """Return True while a P1 slot is active.

    Workers call this before processing each batch item::

        for item in batch:
            if await is_preempted():
                break
            await process(item)
    """
    r = get_redis(REDIS_DB_CACHE)
    return await r.get(_KEY_PREEMPT) is not None


async def get_thermal_state() -> ThermalState:
    """Read current thermal pressure from Redis.

    Returns NOMINAL when the key is absent (manager app not yet running).
    Returns NOMINAL and logs a warning when the stored value is unrecognised.
    """
    r = get_redis(REDIS_DB_CACHE)
    raw = await r.get(_KEY_THERMAL)
    if raw is None:
        return ThermalState.NOMINAL
    try:
        return ThermalState(raw)
    except ValueError:
        logger.warning("rc_thermal_state_unknown", raw_value=raw)
        return ThermalState.NOMINAL


async def get_p4_batch_size(default: int) -> int:
    """Return the effective P4 batch size after applying thermal throttling.

    • NOMINAL / FAIR   → *default* unchanged
    • SERIOUS          → *default* // 2 (minimum 1)
    • CRITICAL         → 0 (caller should skip the batch entirely)
    """
    thermal = await get_thermal_state()
    if thermal == ThermalState.CRITICAL:
        return 0
    if thermal == ThermalState.SERIOUS:
        return max(1, default // 2)
    return default
