"""Unit tests for infra/backup/rotate.py (S08-004).

Tests the backup rotation logic in isolation — no Docker required.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Resolve the infra/backup path relative to the repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "infra" / "backup"))

from rotate import (  # noqa: E402
    DAILY_KEEP,
    WEEKLY_KEEP,
    parse_timestamp,
    rotate_backups,
    select_backups_to_keep,
)


# ---------------------------------------------------------------------------
# parse_timestamp
# ---------------------------------------------------------------------------


def test_parse_timestamp_valid():
    result = parse_timestamp("2026-04-10_14-00-00")
    assert result == datetime(2026, 4, 10, 14, 0, 0)


def test_parse_timestamp_invalid_returns_none():
    assert parse_timestamp("not-a-timestamp") is None
    assert parse_timestamp("2026-04-10") is None
    assert parse_timestamp("README.md") is None


# ---------------------------------------------------------------------------
# select_backups_to_keep
# ---------------------------------------------------------------------------


def _fake_dirs(dates: list[datetime], base: Path | None = None) -> list[Path]:
    """Create mock Path objects with names matching backup timestamp format."""
    base = base or Path("/backups")
    return [base / d.strftime("%Y-%m-%d_%H-%M-%S") for d in dates]


def test_keeps_seven_most_recent_as_dailies():
    """The 7 newest backups are classified as daily."""
    now = datetime(2026, 4, 10, 2, 0, 0)
    dates = [now - timedelta(days=i) for i in range(10)]
    dirs = _fake_dirs(dates)

    dailies, weeklies, to_delete = select_backups_to_keep(dirs)

    assert len(dailies) == DAILY_KEEP  # 7
    assert len(dailies) + len(weeklies) + len(to_delete) == 10


def test_keeps_sunday_backups_as_weeklies():
    """Sunday backups older than the 7-day window are kept as weeklies."""
    # Build backups: 7 recent dailies + several older ones including Sundays
    now = datetime(2026, 4, 13, 2, 0, 0)  # Monday
    dailies_dates = [now - timedelta(days=i) for i in range(DAILY_KEEP)]

    # Two Sunday backups beyond the daily window
    sunday_1 = datetime(2026, 3, 29, 2, 0, 0)  # weekday=6
    sunday_2 = datetime(2026, 3, 22, 2, 0, 0)  # weekday=6
    assert sunday_1.weekday() == 6
    assert sunday_2.weekday() == 6

    non_sunday_old = datetime(2026, 3, 20, 2, 0, 0)  # Friday

    all_dates = dailies_dates + [sunday_1, sunday_2, non_sunday_old]
    dirs = _fake_dirs(all_dates)

    dailies, weeklies, to_delete = select_backups_to_keep(dirs)

    assert len(dailies) == DAILY_KEEP
    assert len(weeklies) == 2  # both Sundays kept
    assert len(to_delete) == 1  # non-Sunday old backup deleted
    # Verify the non-sunday old backup is in to_delete
    deleted_names = {p.name for p in to_delete}
    assert non_sunday_old.strftime("%Y-%m-%d_%H-%M-%S") in deleted_names


def test_caps_weeklies_at_four():
    """At most 4 weekly backups are kept."""
    now = datetime(2026, 4, 13, 2, 0, 0)  # Monday
    dailies_dates = [now - timedelta(days=i) for i in range(DAILY_KEEP)]

    # 6 Sunday backups beyond the daily window — only 4 should be kept
    sundays = [datetime(2026, 3, 29, 2, 0, 0) - timedelta(weeks=i) for i in range(6)]
    for s in sundays:
        assert s.weekday() == 6

    dirs = _fake_dirs(dailies_dates + sundays)
    dailies, weeklies, to_delete = select_backups_to_keep(dirs)

    assert len(weeklies) == WEEKLY_KEEP  # capped at 4
    assert len(to_delete) == 2  # 2 oldest Sundays deleted


def test_fewer_than_seven_backups_all_kept():
    """When fewer than 7 backups exist, all are kept as dailies."""
    now = datetime(2026, 4, 10, 2, 0, 0)
    dates = [now - timedelta(days=i) for i in range(3)]
    dirs = _fake_dirs(dates)

    dailies, weeklies, to_delete = select_backups_to_keep(dirs)

    assert len(dailies) == 3
    assert weeklies == []
    assert to_delete == []


def test_unparseable_dirs_excluded():
    """Directories that don't match the timestamp format are excluded from rotation."""
    parseable = [Path("/backups/2026-04-10_02-00-00")]
    not_parseable = [Path("/backups/manual-backup"), Path("/backups/README.md")]

    dailies, weeklies, to_delete = select_backups_to_keep(parseable + not_parseable)

    kept_names = {p.name for p in dailies + weeklies}
    assert "2026-04-10_02-00-00" in kept_names
    # Unparseable dirs are silently excluded (not in any category)
    assert "manual-backup" not in {p.name for p in dailies + weeklies + to_delete}


# ---------------------------------------------------------------------------
# rotate_backups (filesystem integration)
# ---------------------------------------------------------------------------


def test_rotate_backups_deletes_old_dirs(tmp_path):
    """rotate_backups deletes the correct directories."""
    now = datetime(2026, 4, 10, 2, 0, 0)

    # Create 9 directories: 7 recent + 2 old non-Sundays
    all_dates = [now - timedelta(days=i) for i in range(DAILY_KEEP + 2)]
    for d in all_dates:
        (tmp_path / d.strftime("%Y-%m-%d_%H-%M-%S")).mkdir()

    summary = rotate_backups(tmp_path, dry_run=False)

    assert summary["kept_daily"] == DAILY_KEEP
    assert summary["deleted"] == 2
    assert len(list(tmp_path.iterdir())) == DAILY_KEEP


def test_rotate_backups_dry_run_does_not_delete(tmp_path):
    """dry_run=True reports what would be deleted without deleting anything."""
    now = datetime(2026, 4, 10, 2, 0, 0)
    all_dates = [now - timedelta(days=i) for i in range(10)]
    for d in all_dates:
        (tmp_path / d.strftime("%Y-%m-%d_%H-%M-%S")).mkdir()

    rotate_backups(tmp_path, dry_run=True)

    # All 10 directories still present
    assert len(list(tmp_path.iterdir())) == 10


def test_rotate_backups_nonexistent_dir_returns_empty(capsys):
    """rotate_backups on a missing directory returns zero counts."""
    summary = rotate_backups(Path("/nonexistent/path/does-not-exist"))
    assert summary == {"kept_daily": 0, "kept_weekly": 0, "deleted": 0}


def test_rotate_backups_preserves_sunday_weeklies(tmp_path):
    """Sunday backups beyond the daily window survive rotation."""
    now = datetime(2026, 4, 13, 2, 0, 0)  # Monday
    dailies_dates = [now - timedelta(days=i) for i in range(DAILY_KEEP)]

    sunday = datetime(2026, 3, 29, 2, 0, 0)  # weekday=6
    assert sunday.weekday() == 6
    non_sunday_old = datetime(2026, 3, 20, 2, 0, 0)

    for d in dailies_dates + [sunday, non_sunday_old]:
        (tmp_path / d.strftime("%Y-%m-%d_%H-%M-%S")).mkdir()

    rotate_backups(tmp_path, dry_run=False)

    remaining = {d.name for d in tmp_path.iterdir()}
    assert sunday.strftime("%Y-%m-%d_%H-%M-%S") in remaining
    assert non_sunday_old.strftime("%Y-%m-%d_%H-%M-%S") not in remaining
