"""Regex patterns for deterministic query classification.

Each pattern maps to an intent type and extracts named groups (e.g. a date
reference).  Patterns are tested in order; the first match wins.

Security: extracted groups are used only as parameters to `date_parser` or as
bind-params to parameterized SQL — never interpolated into query strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentType = Literal[
    "calendar_range",
    "reminders_range",
    "contact_search",
    "contact_by_org",
]


@dataclass(frozen=True, slots=True)
class QueryIntent:
    """Result of classifying a user query against the pattern set."""

    intent_type: IntentType
    params: dict[str, str]
    confidence: Literal["deterministic"] = "deterministic"


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Each entry: (compiled regex, intent_type, param-extraction function).
# The extraction function receives the Match and returns a params dict.


def _date_ref(m: re.Match) -> dict[str, str]:
    """Extract the date_ref group from a match."""
    return {"date_ref": m.group("date_ref").strip()}


def _contact_name(m: re.Match) -> dict[str, str]:
    return {"name": m.group("name").strip()}


def _contact_org(m: re.Match) -> dict[str, str]:
    return {"organization": m.group("org").strip()}


_PATTERNS: list[tuple[re.Pattern, IntentType, callable]] = [
    # ── Calendar ──
    (
        re.compile(
            r"what(?:'s| is) on (?:my )?calendar (?P<date_ref>today|tomorrow|yesterday|this week|next week|last week)",
            re.IGNORECASE,
        ),
        "calendar_range",
        _date_ref,
    ),
    (
        re.compile(
            r"(?:show|list|get)(?: me)? (?:my )?(?:calendar|schedule|agenda) (?:for )?(?P<date_ref>today|tomorrow|yesterday|this week|next week|last week)",
            re.IGNORECASE,
        ),
        "calendar_range",
        _date_ref,
    ),
    (
        re.compile(
            r"(?:meetings?|events?|appointments?) (?:for )?(?P<date_ref>today|tomorrow|yesterday|this week|next week|last week)",
            re.IGNORECASE,
        ),
        "calendar_range",
        _date_ref,
    ),
    (
        re.compile(
            r"(?:do i have|are there) (?:any )?(?:meetings?|events?|appointments?) (?P<date_ref>today|tomorrow|this week|next week)",
            re.IGNORECASE,
        ),
        "calendar_range",
        _date_ref,
    ),
    # ── Reminders ──
    (
        re.compile(
            r"(?:what|show|show me|list|get)(?: my)? reminders? (?:that are |are )?(?P<date_ref>due today|overdue|due tomorrow|due this week|due next week)",
            re.IGNORECASE,
        ),
        "reminders_range",
        lambda m: {"date_ref": m.group("date_ref").strip()},
    ),
    (
        re.compile(
            r"what(?:'s| is) (?:due|overdue) (?P<date_ref>today|tomorrow|this week|next week)",
            re.IGNORECASE,
        ),
        "reminders_range",
        lambda m: {"date_ref": m.group("date_ref").strip()},
    ),
    (
        re.compile(
            r"(?:show|list|get)(?: me)?(?: my)? (?:overdue|pending) (?:reminders?|tasks?|todos?)",
            re.IGNORECASE,
        ),
        "reminders_range",
        lambda _: {"date_ref": "overdue"},
    ),
    # ── Contacts ──
    (
        re.compile(
            r"(?:find|show me|search|look up)(?: a)? contact (?:named |for |called )?(?P<name>.+)",
            re.IGNORECASE,
        ),
        "contact_search",
        _contact_name,
    ),
    (
        re.compile(
            r"who is (?P<name>.+)",
            re.IGNORECASE,
        ),
        "contact_search",
        _contact_name,
    ),
    (
        re.compile(
            r"who works at (?P<org>.+)",
            re.IGNORECASE,
        ),
        "contact_by_org",
        _contact_org,
    ),
    (
        re.compile(
            r"(?:people|contacts?|employees?) (?:at|from|in) (?P<org>.+)",
            re.IGNORECASE,
        ),
        "contact_by_org",
        _contact_org,
    ),
]


def classify_query(text: str) -> QueryIntent | None:
    """Match *text* against the deterministic pattern set.

    Returns a QueryIntent on the first match, or None if no pattern matches.
    """
    text = text.strip()
    if not text:
        return None

    for pattern, intent_type, extractor in _PATTERNS:
        m = pattern.fullmatch(text) or pattern.search(text)
        if m:
            params = extractor(m)
            return QueryIntent(intent_type=intent_type, params=params)

    return None
