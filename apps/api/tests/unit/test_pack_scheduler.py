"""Unit tests for PackScheduler time-computation and health (S14-005).

These tests exercise the time-resolution helpers and the health
reporting method. The actual asyncio loops are not run — that
requires the live DB session. The loop correctness is validated
by manual trigger tests (S14-004) and integration tests.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest

from api.services.pack.scheduler import (
    PackScheduler,
    _next_daily,
    _next_weekly,
    _parse_hhmm,
)


class TestParseHHMM:
    def test_morning(self):
        t = _parse_hhmm("06:00")
        assert t.hour == 6
        assert t.minute == 0

    def test_midnight(self):
        t = _parse_hhmm("00:00")
        assert t.hour == 0

    def test_late_night(self):
        t = _parse_hhmm("23:59")
        assert t.hour == 23
        assert t.minute == 59


class TestNextDaily:
    def test_before_run_time_today(self):
        run_time = time(14, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
        result = _next_daily(run_time, now)
        assert result == datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)

    def test_after_run_time_tomorrow(self):
        run_time = time(6, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)
        result = _next_daily(run_time, now)
        assert result.date() == datetime(2026, 4, 16).date()
        assert result.hour == 6

    def test_exactly_at_run_time_tomorrow(self):
        run_time = time(8, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
        result = _next_daily(run_time, now)
        assert result.date() == datetime(2026, 4, 16).date()


class TestNextWeekly:
    def test_monday_before_target(self):
        # now is Sunday, target Monday 08:00
        now = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)  # Sunday
        assert now.weekday() == 6
        result = _next_weekly("monday", time(8, 0, tzinfo=timezone.utc), now)
        assert result.weekday() == 0
        assert result > now

    def test_monday_after_target_this_week(self):
        # now is Monday 18:00, target Monday 08:00 → next Monday
        now = datetime(2026, 4, 13, 18, 0, tzinfo=timezone.utc)  # Monday
        assert now.weekday() == 0
        result = _next_weekly("monday", time(8, 0, tzinfo=timezone.utc), now)
        assert result > now
        assert result.weekday() == 0
        assert (result - now).days == 7 or (result - now).days == 6

    def test_friday(self):
        now = datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc)  # Tuesday
        result = _next_weekly("friday", time(9, 0, tzinfo=timezone.utc), now)
        assert result.weekday() == 4
        assert result > now


class TestSchedulerHealth:
    def test_health_when_stopped(self):
        from unittest.mock import MagicMock

        scheduler = PackScheduler(
            runner=MagicMock(),
            manifest_loader=MagicMock(manifests={}),
        )
        h = scheduler.health()
        assert h["running"] is False
        assert h["jobs_registered"] == 0
        assert h["next_daily_run"] is None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_health_after_start(self):
        from unittest.mock import MagicMock

        from api.services.pack.manifest_loader import (
            ManifestLoader,
            PackManifest,
            ResourceLimits,
            ScheduleConfig,
        )

        manifest = PackManifest(
            pack_id="tst",
            name="Test",
            version="1.0.0",
            description="t",
            author="t",
            capabilities=["read:contacts"],
            resource_limits=ResourceLimits(
                max_execution_time_seconds=10,
                max_memory_mb=10,
                max_llm_calls_per_run=1,
            ),
            card_types=["x"],
            schedule=ScheduleConfig(daily="06:00", weekly="monday 08:00"),
        )
        loader = ManifestLoader(packs_dir="/dev/null")
        loader._manifests["tst"] = manifest

        scheduler = PackScheduler(
            runner=MagicMock(),
            manifest_loader=loader,
        )
        await scheduler.start()
        try:
            h = scheduler.health()
            assert h["running"] is True
            assert h["jobs_registered"] == 2
        finally:
            await scheduler.stop()
        h2 = scheduler.health()
        assert h2["running"] is False
        assert h2["jobs_registered"] == 0
