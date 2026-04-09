"""Parse natural-language date references into UTC (start, end) datetime tuples.

Supported references:
  today, tomorrow, yesterday, this week, next week, last week

All results are UTC-based. Weeks start on Monday.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

_WEEK_START = 0  # Monday


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    """Return (start-of-day, end-of-day) in UTC for a calendar date."""
    start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    end = datetime.combine(d, time.max, tzinfo=timezone.utc)
    return start, end


def _week_bounds(d: date) -> tuple[datetime, datetime]:
    """Return (Monday 00:00, Sunday 23:59:59) of the week containing *d*."""
    monday = d - timedelta(days=(d.weekday() - _WEEK_START) % 7)
    sunday = monday + timedelta(days=6)
    return _day_bounds(monday)[0], _day_bounds(sunday)[1]


def parse_date_reference(
    ref: str,
    *,
    reference_date: date | None = None,
) -> tuple[datetime, datetime] | None:
    """Parse a date reference string into a (start, end) UTC datetime pair.

    Returns None if the reference is not recognised.
    """
    today = reference_date or datetime.now(timezone.utc).date()
    ref = ref.strip().lower()

    if ref == "today":
        return _day_bounds(today)

    if ref == "tomorrow":
        return _day_bounds(today + timedelta(days=1))

    if ref == "yesterday":
        return _day_bounds(today - timedelta(days=1))

    if ref in ("this week",):
        return _week_bounds(today)

    if ref in ("next week",):
        return _week_bounds(today + timedelta(weeks=1))

    if ref in ("last week",):
        return _week_bounds(today - timedelta(weeks=1))

    return None
