"""Tests for S04-001: Resource controller.

Covers:
  - P1 acquires immediately and is not blocked by P3/P4 pressure
  - P4 blocks when both P4 slots are taken
  - Slot is released cleanly after the context manager exits
  - P1 acquire triggers preempt signal; is_preempted() returns True
  - P1 exit clears preempt signal; is_preempted() returns False
  - P4 acquire raises ResourceThrottledError when thermal=CRITICAL
  - P3 acquire raises ResourceThrottledError when thermal=CRITICAL
  - SERIOUS thermal halves get_p4_batch_size; NOMINAL returns full size
  - get_thermal_state falls back to NOMINAL for missing/unknown keys
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.resource_controller import (
    Priority,
    ResourceThrottledError,
    ThermalState,
    _KEY_PREEMPT,
    _KEY_THERMAL,
    acquire_slot,
    get_p4_batch_size,
    get_thermal_state,
    is_preempted,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_redis_mock(
    *,
    preempt_value: str | None = None,
    thermal_value: str | None = None,
) -> MagicMock:
    """Return a mock redis client with configurable key reads."""
    mock = MagicMock()

    async def _get(key: str) -> str | None:
        if key == _KEY_PREEMPT:
            return preempt_value
        if key == _KEY_THERMAL:
            return thermal_value
        return None

    mock.get = _get
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.publish = AsyncMock(return_value=1)
    return mock


def _patch_redis(
    *,
    preempt_value: str | None = None,
    thermal_value: str | None = None,
):
    """Patch get_redis in resource_controller with a pre-configured mock."""
    redis_mock = _make_redis_mock(
        preempt_value=preempt_value,
        thermal_value=thermal_value,
    )
    return patch(
        "api.services.resource_controller.get_redis",
        return_value=redis_mock,
    ), redis_mock


# ---------------------------------------------------------------------------
# Priority slot tests
# ---------------------------------------------------------------------------


class TestPrioritySlots:
    @pytest.mark.asyncio
    async def test_p1_acquires_immediately(self):
        """P1 must acquire its single slot without waiting."""
        patcher, _ = _patch_redis()
        with patcher:
            acquired = False
            async with acquire_slot(Priority.P1_INTERACTIVE):
                acquired = True
            assert acquired

    @pytest.mark.asyncio
    async def test_p2_acquires_immediately(self):
        patcher, _ = _patch_redis()
        with patcher:
            acquired = False
            async with acquire_slot(Priority.P2_PACK):
                acquired = True
            assert acquired

    @pytest.mark.asyncio
    async def test_p3_acquires_when_slots_available(self):
        patcher, _ = _patch_redis()
        with patcher:
            acquired = False
            async with acquire_slot(Priority.P3_BACKGROUND_IMPORTANT):
                acquired = True
            assert acquired

    @pytest.mark.asyncio
    async def test_p4_acquires_when_slots_available(self):
        patcher, _ = _patch_redis()
        with patcher:
            acquired = False
            async with acquire_slot(Priority.P4_BACKGROUND_LOW):
                acquired = True
            assert acquired

    @pytest.mark.asyncio
    async def test_p4_waits_when_both_slots_full(self):
        """A third P4 acquire must block when both P4 slots are occupied."""
        patcher, _ = _patch_redis()
        with patcher:
            # Directly exhaust the semaphore for this loop
            from api.services.resource_controller import _get_semaphore

            sem = _get_semaphore(Priority.P4_BACKGROUND_LOW)
            # Drain both slots
            await sem.acquire()
            await sem.acquire()

            acquired = False

            async def _try_acquire() -> None:
                nonlocal acquired
                await sem.acquire()
                acquired = True
                sem.release()

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(_try_acquire(), timeout=0.05)

            assert not acquired, "Third P4 slot must not be granted while both are taken"

            # Restore semaphore state for subsequent tests on this loop
            sem.release()
            sem.release()

    @pytest.mark.asyncio
    async def test_slot_released_after_context_exit(self):
        """Slot count must be restored after the context manager exits."""
        patcher, _ = _patch_redis()
        with patcher:
            from api.services.resource_controller import _get_semaphore

            sem = _get_semaphore(Priority.P2_PACK)
            before = sem._value  # BoundedSemaphore internal counter

            async with acquire_slot(Priority.P2_PACK):
                assert sem._value == before - 1

            assert sem._value == before

    @pytest.mark.asyncio
    async def test_slot_released_even_on_exception(self):
        """Slot must be released even when the body raises."""
        patcher, _ = _patch_redis()
        with patcher:
            from api.services.resource_controller import _get_semaphore

            sem = _get_semaphore(Priority.P2_PACK)
            before = sem._value

            with pytest.raises(RuntimeError):
                async with acquire_slot(Priority.P2_PACK):
                    raise RuntimeError("body error")

            assert sem._value == before


# ---------------------------------------------------------------------------
# Preempt signal tests
# ---------------------------------------------------------------------------


class TestPreemptSignal:
    @pytest.mark.asyncio
    async def test_p1_sets_preempt_key_on_acquire(self):
        """Entering a P1 slot must call setex on the preempt key."""
        patcher, redis_mock = _patch_redis()
        with patcher:
            async with acquire_slot(Priority.P1_INTERACTIVE):
                redis_mock.setex.assert_awaited_once_with(
                    _KEY_PREEMPT, 30, "1"
                )

    @pytest.mark.asyncio
    async def test_p1_publishes_preempt_on_acquire(self):
        """P1 must publish to the rc:preempt pub/sub channel on entry."""
        patcher, redis_mock = _patch_redis()
        with patcher:
            async with acquire_slot(Priority.P1_INTERACTIVE):
                redis_mock.publish.assert_awaited_once_with(_KEY_PREEMPT, "preempt")

    @pytest.mark.asyncio
    async def test_p1_clears_preempt_on_exit(self):
        """P1 must delete the preempt key when the slot is released."""
        patcher, redis_mock = _patch_redis()
        with patcher:
            async with acquire_slot(Priority.P1_INTERACTIVE):
                pass  # exit immediately
        redis_mock.delete.assert_awaited_once_with(_KEY_PREEMPT)

    @pytest.mark.asyncio
    async def test_p1_clears_preempt_even_on_exception(self):
        """Preempt key must be cleared even when the P1 body raises."""
        patcher, redis_mock = _patch_redis()
        with patcher:
            with pytest.raises(ValueError):
                async with acquire_slot(Priority.P1_INTERACTIVE):
                    raise ValueError("simulated error")
        redis_mock.delete.assert_awaited_once_with(_KEY_PREEMPT)

    @pytest.mark.asyncio
    async def test_is_preempted_true_when_key_set(self):
        """is_preempted() returns True when rc:preempt key exists."""
        patcher, _ = _patch_redis(preempt_value="1")
        with patcher:
            assert await is_preempted() is True

    @pytest.mark.asyncio
    async def test_is_preempted_false_when_key_absent(self):
        """is_preempted() returns False when rc:preempt key is absent."""
        patcher, _ = _patch_redis(preempt_value=None)
        with patcher:
            assert await is_preempted() is False

    @pytest.mark.asyncio
    async def test_p2_does_not_set_preempt(self):
        """P2 slot must NOT trigger preempt signalling."""
        patcher, redis_mock = _patch_redis()
        with patcher:
            async with acquire_slot(Priority.P2_PACK):
                pass
        redis_mock.setex.assert_not_awaited()
        redis_mock.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_p3_does_not_set_preempt(self):
        """P3 slot must NOT trigger preempt signalling."""
        patcher, redis_mock = _patch_redis()
        with patcher:
            async with acquire_slot(Priority.P3_BACKGROUND_IMPORTANT):
                pass
        redis_mock.setex.assert_not_awaited()


# ---------------------------------------------------------------------------
# Thermal awareness tests
# ---------------------------------------------------------------------------


class TestThermalAwareness:
    @pytest.mark.asyncio
    async def test_p4_raises_on_critical_thermal(self):
        """P4 acquire_slot raises ResourceThrottledError when thermal=critical."""
        patcher, _ = _patch_redis(thermal_value="critical")
        with patcher:
            with pytest.raises(ResourceThrottledError) as exc_info:
                async with acquire_slot(Priority.P4_BACKGROUND_LOW):
                    pass
        assert exc_info.value.priority == Priority.P4_BACKGROUND_LOW
        assert exc_info.value.reason == "thermal_critical"

    @pytest.mark.asyncio
    async def test_p3_raises_on_critical_thermal(self):
        """P3 acquire_slot raises ResourceThrottledError when thermal=critical."""
        patcher, _ = _patch_redis(thermal_value="critical")
        with patcher:
            with pytest.raises(ResourceThrottledError) as exc_info:
                async with acquire_slot(Priority.P3_BACKGROUND_IMPORTANT):
                    pass
        assert exc_info.value.priority == Priority.P3_BACKGROUND_IMPORTANT

    @pytest.mark.asyncio
    async def test_p1_not_blocked_by_critical_thermal(self):
        """P1 interactive must never be blocked by thermal state."""
        patcher, _ = _patch_redis(thermal_value="critical")
        with patcher:
            acquired = False
            async with acquire_slot(Priority.P1_INTERACTIVE):
                acquired = True
            assert acquired

    @pytest.mark.asyncio
    async def test_p2_not_blocked_by_critical_thermal(self):
        """P2 pack execution must not be blocked by thermal state."""
        patcher, _ = _patch_redis(thermal_value="critical")
        with patcher:
            acquired = False
            async with acquire_slot(Priority.P2_PACK):
                acquired = True
            assert acquired

    @pytest.mark.asyncio
    async def test_p4_proceeds_on_serious_thermal(self):
        """P4 acquire must succeed on SERIOUS thermal (only batch size is halved)."""
        patcher, _ = _patch_redis(thermal_value="serious")
        with patcher:
            acquired = False
            async with acquire_slot(Priority.P4_BACKGROUND_LOW):
                acquired = True
            assert acquired

    @pytest.mark.asyncio
    async def test_get_p4_batch_size_serious_halves(self):
        """SERIOUS thermal must halve the batch size (minimum 1)."""
        patcher, _ = _patch_redis(thermal_value="serious")
        with patcher:
            assert await get_p4_batch_size(100) == 50
            assert await get_p4_batch_size(1) == 1   # minimum floor
            assert await get_p4_batch_size(3) == 1   # 3//2 = 1

    @pytest.mark.asyncio
    async def test_get_p4_batch_size_critical_returns_zero(self):
        """CRITICAL thermal must return batch size 0 (caller skips entirely)."""
        patcher, _ = _patch_redis(thermal_value="critical")
        with patcher:
            assert await get_p4_batch_size(50) == 0

    @pytest.mark.asyncio
    async def test_get_p4_batch_size_nominal_unchanged(self):
        """NOMINAL thermal must return the default batch size unchanged."""
        patcher, _ = _patch_redis(thermal_value=None)
        with patcher:
            assert await get_p4_batch_size(50) == 50

    @pytest.mark.asyncio
    async def test_get_p4_batch_size_fair_unchanged(self):
        """FAIR thermal must return the default batch size unchanged."""
        patcher, _ = _patch_redis(thermal_value="fair")
        with patcher:
            assert await get_p4_batch_size(50) == 50


# ---------------------------------------------------------------------------
# Thermal state reading
# ---------------------------------------------------------------------------


class TestGetThermalState:
    @pytest.mark.asyncio
    async def test_defaults_to_nominal_when_key_absent(self):
        patcher, _ = _patch_redis(thermal_value=None)
        with patcher:
            assert await get_thermal_state() == ThermalState.NOMINAL

    @pytest.mark.asyncio
    async def test_returns_nominal(self):
        patcher, _ = _patch_redis(thermal_value="nominal")
        with patcher:
            assert await get_thermal_state() == ThermalState.NOMINAL

    @pytest.mark.asyncio
    async def test_returns_fair(self):
        patcher, _ = _patch_redis(thermal_value="fair")
        with patcher:
            assert await get_thermal_state() == ThermalState.FAIR

    @pytest.mark.asyncio
    async def test_returns_serious(self):
        patcher, _ = _patch_redis(thermal_value="serious")
        with patcher:
            assert await get_thermal_state() == ThermalState.SERIOUS

    @pytest.mark.asyncio
    async def test_returns_critical(self):
        patcher, _ = _patch_redis(thermal_value="critical")
        with patcher:
            assert await get_thermal_state() == ThermalState.CRITICAL

    @pytest.mark.asyncio
    async def test_unknown_value_falls_back_to_nominal(self):
        """An unrecognised thermal value must log a warning and return NOMINAL."""
        patcher, _ = _patch_redis(thermal_value="turbo_hot")
        with patcher:
            result = await get_thermal_state()
        assert result == ThermalState.NOMINAL
