"""Parse natural-language date references into UTC (start, end) datetime tuples.

Supported references:
  today, tomorrow, yesterday
  this week, next week, last week
  this morning, this afternoon, this evening, tonight
  on monday, on tuesday, ... (next occurrence)
  on march 25, on jan 3, on 2026-04-15

All results are UTC-based. Weeks start on Monday.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

_WEEK_START = 0  # Monday

_WEEKDAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Time-of-day boundaries (hours, UTC)
_TIME_MORNING = (6, 12)
_TIME_AFTERNOON = (12, 17)
_TIME_EVENING = (17, 21)
_TIME_NIGHT = (21, 24)

_DATE_MONTH_DAY_RE = re.compile(
    r"(?P<month>[a-z]+)\s+(?P<day>\d{1,2})",
    re.IGNORECASE,
)
_DATE_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    """Return (start-of-day, end-of-day) in UTC for a calendar date."""
    start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    end = datetime.combine(d, time.max, tzinfo=timezone.utc)
    return start, end


def _time_range(d: date, hour_start: int, hour_end: int) -> tuple[datetime, datetime]:
    """Return a time range within a single day."""
    start = datetime.combine(d, time(hour_start, 0), tzinfo=timezone.utc)
    # hour_end=24 means end of day
    if hour_end >= 24:
        end = datetime.combine(d, time.max, tzinfo=timezone.utc)
    else:
        end = datetime.combine(d, time(hour_end, 0), tzinfo=timezone.utc) - timedelta(seconds=1)
    return start, end


def _week_bounds(d: date) -> tuple[datetime, datetime]:
    """Return (Monday 00:00, Sunday 23:59:59) of the week containing *d*."""
    monday = d - timedelta(days=(d.weekday() - _WEEK_START) % 7)
    sunday = monday + timedelta(days=6)
    return _day_bounds(monday)[0], _day_bounds(sunday)[1]


def _next_weekday(today: date, weekday: int) -> date:
    """Return the next occurrence of *weekday* (0=Mon) after today."""
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def _parse_month_day(text: str, today: date) -> date | None:
    """Try to parse 'march 25' or 'jan 3' into a date."""
    m = _DATE_MONTH_DAY_RE.match(text)
    if not m:
        return None
    month_name = m.group("month").lower()
    month = _MONTH_NAMES.get(month_name)
    if month is None:
        return None
    day = int(m.group("day"))
    try:
        return date(today.year, month, day)
    except ValueError:
        return None


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

    # Simple day references
    if ref == "today":
        return _day_bounds(today)
    if ref == "tomorrow":
        return _day_bounds(today + timedelta(days=1))
    if ref == "yesterday":
        return _day_bounds(today - timedelta(days=1))

    # Week references
    if ref == "this week":
        return _week_bounds(today)
    if ref == "next week":
        return _week_bounds(today + timedelta(weeks=1))
    if ref == "last week":
        return _week_bounds(today - timedelta(weeks=1))

    # Time-of-day references
    if ref in ("this morning", "morning"):
        return _time_range(today, *_TIME_MORNING)
    if ref in ("this afternoon", "afternoon"):
        return _time_range(today, *_TIME_AFTERNOON)
    if ref in ("this evening", "evening"):
        return _time_range(today, *_TIME_EVENING)
    if ref in ("tonight", "this night", "night"):
        return _time_range(today, *_TIME_NIGHT)

    # "on monday", "on friday", etc.
    stripped = ref.removeprefix("on ").strip()
    if stripped in _WEEKDAY_NAMES:
        target = _next_weekday(today, _WEEKDAY_NAMES[stripped])
        return _day_bounds(target)

    # "on march 25", "on jan 3"
    parsed_date = _parse_month_day(stripped, today)
    if parsed_date is not None:
        return _day_bounds(parsed_date)

    # ISO date "2026-04-15"
    if _DATE_ISO_RE.fullmatch(stripped):
        try:
            return _day_bounds(date.fromisoformat(stripped))
        except ValueError:
            pass

    # "last 7 days", "past week"
    if ref in ("last 7 days", "past week", "past 7 days"):
        start = today - timedelta(days=6)
        return _day_bounds(start)[0], _day_bounds(today)[1]

    # "last 30 days", "past month"
    if ref in ("last 30 days", "past month", "past 30 days"):
        start = today - timedelta(days=29)
        return _day_bounds(start)[0], _day_bounds(today)[1]

    return None
