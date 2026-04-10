#!/usr/bin/env python3
"""Backup rotation for EkamCore (S08-004).

Policy:
  - Keep the 7 most recent backups (daily retention).
  - From backups older than those 7, keep up to 4 that fell on a Sunday
    (weekly retention anchors).
  - Delete everything else.

Backup directory name format: YYYY-MM-DD_HH-MM-SS

Usage:
    python3 rotate.py --backup-dir /backups [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


DAILY_KEEP = 7
WEEKLY_KEEP = 4
TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


def parse_timestamp(name: str) -> datetime | None:
    """Parse a backup directory name into a datetime. Returns None on failure."""
    try:
        return datetime.strptime(name, TIMESTAMP_FORMAT)
    except ValueError:
        return None


def select_backups_to_keep(
    dirs: list[Path],
) -> tuple[list[Path], list[Path], list[Path]]:
    """Categorize backup directories.

    Returns (dailies, weeklies, to_delete).
    - dailies: the most recent DAILY_KEEP backups
    - weeklies: up to WEEKLY_KEEP Sunday backups from older entries
    - to_delete: everything else
    """
    # Only consider directories whose names parse as timestamps
    timestamped: list[tuple[datetime, Path]] = []
    unparseable: list[Path] = []

    for d in dirs:
        ts = parse_timestamp(d.name)
        if ts is not None:
            timestamped.append((ts, d))
        else:
            unparseable.append(d)

    # Sort newest first
    timestamped.sort(key=lambda x: x[0], reverse=True)

    dailies: list[Path] = []
    weeklies: list[Path] = []
    to_delete: list[Path] = []

    for i, (ts, path) in enumerate(timestamped):
        if i < DAILY_KEEP:
            dailies.append(path)
        elif ts.weekday() == 6 and len(weeklies) < WEEKLY_KEEP:  # Sunday
            weeklies.append(path)
        else:
            to_delete.append(path)

    return dailies, weeklies, to_delete


def rotate_backups(backup_root: Path, dry_run: bool = False) -> dict[str, int]:
    """Run rotation against backup_root.

    Returns a summary dict with counts of kept_daily, kept_weekly, deleted.
    """
    if not backup_root.exists():
        print(f"Backup directory does not exist: {backup_root}", file=sys.stderr)
        return {"kept_daily": 0, "kept_weekly": 0, "deleted": 0}

    dirs = [d for d in backup_root.iterdir() if d.is_dir()]
    dailies, weeklies, to_delete = select_backups_to_keep(dirs)

    for path in to_delete:
        if dry_run:
            print(f"[DRY-RUN] Would delete: {path}")
        else:
            shutil.rmtree(path)
            print(f"Deleted: {path}")

    summary = {
        "kept_daily": len(dailies),
        "kept_weekly": len(weeklies),
        "deleted": len(to_delete),
    }

    print(
        f"Rotation complete: {summary['kept_daily']} daily, "
        f"{summary['kept_weekly']} weekly kept, "
        f"{summary['deleted']} deleted."
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Rotate EkamCore backups")
    parser.add_argument(
        "--backup-dir",
        default="/backups",
        help="Root directory containing timestamped backup folders",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting",
    )
    args = parser.parse_args()

    rotate_backups(Path(args.backup_dir), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
