"""Regex patterns for deterministic query classification.

50+ patterns covering calendar, reminders, contacts, stats, and recent queries.
Patterns are tested in order; the first match wins.

Security: extracted groups are used only as parameters to `date_parser` or as
bind-params to parameterized SQL — never interpolated into query strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentType = Literal[
    "calendar_range",
    "calendar_with_person",
    "calendar_at_location",
    "reminders_range",
    "reminders_by_priority",
    "reminders_by_list",
    "contact_search",
    "contact_by_org",
    "contact_field",
    "count_query",
    "recent_query",
    "photo_date",
    "photo_location",
    "photo_camera",
]


@dataclass(frozen=True, slots=True)
class QueryIntent:
    """Result of classifying a user query against the pattern set."""

    intent_type: IntentType
    params: dict[str, str]
    confidence: Literal["deterministic"] = "deterministic"


# ---------------------------------------------------------------------------
# Common date reference pattern fragment
# ---------------------------------------------------------------------------

_DATE_REF = (
    r"(?P<date_ref>"
    r"today|tomorrow|yesterday|"
    r"this week|next week|last week|"
    r"this morning|this afternoon|this evening|tonight|"
    r"morning|afternoon|evening|"
    r"on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|wed|thu|fri|sat|sun)|"
    r"on [a-z]+ \d{1,2}|"  # "on march 25"
    r"on \d{4}-\d{2}-\d{2}|"  # "on 2026-04-15"
    r"last 7 days|last 30 days|past week|past month"
    r")"
)

_DATE_REF_SIMPLE = (
    r"(?P<date_ref>"
    r"today|tomorrow|yesterday|"
    r"this week|next week|last week|"
    r"this morning|this afternoon|this evening|tonight"
    r")"
)


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

def _date_ref(m: re.Match) -> dict[str, str]:
    return {"date_ref": m.group("date_ref").strip()}

def _contact_name(m: re.Match) -> dict[str, str]:
    return {"name": m.group("name").strip()}

def _contact_org(m: re.Match) -> dict[str, str]:
    return {"organization": m.group("org").strip()}

def _person_date(m: re.Match) -> dict[str, str]:
    return {
        "person": m.group("person").strip(),
        "date_ref": m.group("date_ref").strip(),
    }

def _location(m: re.Match) -> dict[str, str]:
    return {"location": m.group("location").strip()}

def _location_date(m: re.Match) -> dict[str, str]:
    result: dict[str, str] = {"location": m.group("location").strip()}
    try:
        result["date_ref"] = m.group("date_ref").strip()
    except IndexError:
        pass
    return result

def _priority(m: re.Match) -> dict[str, str]:
    raw = m.group("priority").strip().lower()
    # Normalize: urgent → high
    if raw in ("urgent", "important", "critical"):
        raw = "high"
    return {"priority": raw}

def _list_name(m: re.Match) -> dict[str, str]:
    return {"list_name": m.group("list_name").strip()}

def _contact_field(m: re.Match) -> dict[str, str]:
    return {
        "field": m.group("field").strip().lower(),
        "name": m.group("name").strip(),
    }

def _count(m: re.Match) -> dict[str, str]:
    result: dict[str, str] = {"entity": m.group("entity").strip().lower()}
    try:
        result["date_ref"] = m.group("date_ref").strip()
    except IndexError:
        result["date_ref"] = "today"
    return result

def _recent(m: re.Match) -> dict[str, str]:
    return {"entity": m.group("entity").strip().lower()}

def _photo_date(m: re.Match) -> dict[str, str]:
    return {"date_ref": m.group("date_ref").strip()}

def _photo_location(m: re.Match) -> dict[str, str]:
    return {"location": m.group("location").strip()}

def _photo_camera(m: re.Match) -> dict[str, str]:
    return {"camera": m.group("camera").strip()}


# ---------------------------------------------------------------------------
# Pattern list (50+ patterns)
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern, IntentType, callable]] = [

    # ══════════════════════════════════════════════════════════════════════
    # CALENDAR — Range queries
    # ══════════════════════════════════════════════════════════════════════

    # 1. "what's on my calendar today/tomorrow/this week/..."
    (re.compile(rf"what(?:'s| is) on (?:my )?calendar {_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 2. "show/list/get my calendar for today"
    (re.compile(rf"(?:show|list|get)(?: me)? (?:my )?(?:calendar|schedule|agenda) (?:for )?{_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 3. "meetings/events/appointments today"
    (re.compile(rf"(?:meetings?|events?|appointments?) (?:for )?{_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 4. "do I have anything today/tomorrow"
    (re.compile(rf"(?:do i have|are there|is there) (?:anything|any (?:meetings?|events?|appointments?)) {_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 5. "what do I have today"
    (re.compile(rf"what (?:do i have|have i got|am i doing) {_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 6. "morning meetings" / "afternoon events"
    (re.compile(r"(?P<date_ref>morning|afternoon|evening) (?:meetings?|events?|appointments?)", re.I),
     "calendar_range", _date_ref),

    # 7. "my schedule for monday"
    (re.compile(rf"(?:my |the )?(?:schedule|calendar|agenda) (?:for |on )?{_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 8. "what's happening today/tomorrow"
    (re.compile(rf"what(?:'s| is) happening {_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 9. "anything on my calendar this week"
    (re.compile(rf"anything (?:on (?:my )?calendar )?{_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 10. "plans for today"
    (re.compile(rf"(?:my )?plans? (?:for )?{_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # 11. "what's scheduled for tomorrow"
    (re.compile(rf"what(?:'s| is) (?:scheduled|planned) (?:for )?{_DATE_REF}", re.I),
     "calendar_range", _date_ref),

    # ══════════════════════════════════════════════════════════════════════
    # CALENDAR — With person
    # ══════════════════════════════════════════════════════════════════════

    # 12. "meetings with John this week"
    (re.compile(rf"(?:meetings?|events?|appointments?) with (?P<person>.+?) {_DATE_REF_SIMPLE}", re.I),
     "calendar_with_person", _person_date),

    # 13. "do I have anything with Sarah tomorrow"
    (re.compile(rf"(?:do i have|any) (?:anything|meetings?|events?) with (?P<person>.+?) {_DATE_REF_SIMPLE}", re.I),
     "calendar_with_person", _person_date),

    # 14. "when am I meeting John"
    (re.compile(r"when (?:am i|do i) (?:meeting|seeing) (?P<person>.+)", re.I),
     "calendar_with_person", lambda m: {"person": m.group("person").strip(), "date_ref": "this week"}),

    # ══════════════════════════════════════════════════════════════════════
    # CALENDAR — At location
    # ══════════════════════════════════════════════════════════════════════

    # 15. "meetings at Conference Room A"
    (re.compile(r"(?:meetings?|events?|appointments?) (?:at|in) (?P<location>.+)", re.I),
     "calendar_at_location", _location),

    # 16. "what's happening at the office"
    (re.compile(r"what(?:'s| is) (?:happening|scheduled) (?:at|in) (?P<location>.+)", re.I),
     "calendar_at_location", _location),

    # ══════════════════════════════════════════════════════════════════════
    # REMINDERS — Range queries
    # ══════════════════════════════════════════════════════════════════════

    # 17. "show my reminders due today/overdue"
    (re.compile(r"(?:what|show|show me|list|get)(?: my)? reminders? (?:that are |are )?(?P<date_ref>due today|overdue|due tomorrow|due this week|due next week)", re.I),
     "reminders_range", lambda m: {"date_ref": m.group("date_ref").strip()}),

    # 18. "what's due today/tomorrow"
    (re.compile(rf"what(?:'s| is) (?:due|overdue) {_DATE_REF_SIMPLE}", re.I),
     "reminders_range", lambda m: {"date_ref": m.group("date_ref").strip()}),

    # 19. "show overdue/pending tasks"
    (re.compile(r"(?:show|list|get)(?: me)?(?: my)? (?:overdue|pending) (?:reminders?|tasks?|todos?)", re.I),
     "reminders_range", lambda _: {"date_ref": "overdue"}),

    # 20. "what tasks do I have today"
    (re.compile(rf"what (?:tasks?|reminders?|todos?) (?:do i have|are there) {_DATE_REF_SIMPLE}", re.I),
     "reminders_range", _date_ref),

    # 21. "incomplete/open reminders"
    (re.compile(r"(?:incomplete|open|unfinished|undone) (?:reminders?|tasks?|todos?)", re.I),
     "reminders_range", lambda _: {"date_ref": "overdue"}),

    # 22. "my to-do list"
    (re.compile(r"(?:my |the )?(?:to-?do|task) list", re.I),
     "reminders_range", lambda _: {"date_ref": "due today"}),

    # ══════════════════════════════════════════════════════════════════════
    # REMINDERS — By priority
    # ══════════════════════════════════════════════════════════════════════

    # 23. "high priority reminders"
    (re.compile(r"(?P<priority>high|medium|low|urgent|important|critical) (?:priority )?(?:reminders?|tasks?|todos?)", re.I),
     "reminders_by_priority", _priority),

    # 24. "reminders with high priority"
    (re.compile(r"(?:reminders?|tasks?|todos?) (?:with |that are )?(?P<priority>high|medium|low|urgent|important|critical)(?: priority)?", re.I),
     "reminders_by_priority", _priority),

    # 25. "what's urgent"
    (re.compile(r"what(?:'s| is) (?P<priority>urgent|important|critical)", re.I),
     "reminders_by_priority", _priority),

    # ══════════════════════════════════════════════════════════════════════
    # REMINDERS — By list
    # ══════════════════════════════════════════════════════════════════════

    # 26. "reminders in Work"
    (re.compile(r"(?:reminders?|tasks?|todos?) (?:in|from|on) (?:the )?(?:list )?(?P<list_name>.+)", re.I),
     "reminders_by_list", _list_name),

    # 27. "show my Work list"
    (re.compile(r"(?:show|list|get)(?: me)?(?: my)? (?P<list_name>.+?) (?:list|reminders?|tasks?)", re.I),
     "reminders_by_list", _list_name),

    # ══════════════════════════════════════════════════════════════════════
    # CONTACTS — Search
    # ══════════════════════════════════════════════════════════════════════

    # 28. "find/show contact named X"
    (re.compile(r"(?:find|show me|search|look up)(?: a)? contact (?:named |for |called )?(?P<name>.+)", re.I),
     "contact_search", _contact_name),

    # 29. "who is X"
    (re.compile(r"who is (?P<name>.+)", re.I),
     "contact_search", _contact_name),

    # 30. "contact info for X"
    (re.compile(r"contact (?:info|information|details) (?:for |about )?(?P<name>.+)", re.I),
     "contact_search", _contact_name),

    # 31. "tell me about X" (person context)
    (re.compile(r"tell me about (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)+)", re.NOFLAG),
     "contact_search", _contact_name),

    # ══════════════════════════════════════════════════════════════════════
    # CONTACTS — By organization
    # ══════════════════════════════════════════════════════════════════════

    # 32. "who works at X"
    (re.compile(r"who works (?:at|for) (?P<org>.+)", re.I),
     "contact_by_org", _contact_org),

    # 33. "people/contacts at X"
    (re.compile(r"(?:people|contacts?|employees?|colleagues?) (?:at|from|in) (?P<org>.+)", re.I),
     "contact_by_org", _contact_org),

    # 34. "team at X"
    (re.compile(r"(?:the )?team (?:at|from) (?P<org>.+)", re.I),
     "contact_by_org", _contact_org),

    # ══════════════════════════════════════════════════════════════════════
    # CONTACTS — Specific field lookup
    # ══════════════════════════════════════════════════════════════════════

    # 35. "phone number for X"
    (re.compile(r"(?P<field>phone(?: number)?|cell|mobile) (?:for |of )?(?P<name>.+)", re.I),
     "contact_field", _contact_field),

    # 36. "email for X"
    (re.compile(r"(?P<field>email|e-mail)(?: address)? (?:for |of )?(?P<name>.+)", re.I),
     "contact_field", _contact_field),

    # 37. "X's phone/email/birthday"
    (re.compile(r"(?P<name>.+?)(?:'s| 's) (?P<field>phone(?: number)?|email|e-mail|birthday|address)", re.I),
     "contact_field", _contact_field),

    # 38. "what is X's email"
    (re.compile(r"what(?:'s| is) (?P<name>.+?)(?:'s| 's) (?P<field>phone(?: number)?|email|e-mail|birthday|address)", re.I),
     "contact_field", _contact_field),

    # 39. "birthday of X"
    (re.compile(r"(?P<field>birthday|birth date) (?:of |for )?(?P<name>.+)", re.I),
     "contact_field", _contact_field),

    # ══════════════════════════════════════════════════════════════════════
    # STATS — Count queries
    # ══════════════════════════════════════════════════════════════════════

    # 40. "how many events/meetings/reminders today"
    (re.compile(rf"how many (?P<entity>events?|meetings?|appointments?|reminders?|tasks?|todos?|contacts?) (?:do i have )?{_DATE_REF_SIMPLE}", re.I),
     "count_query", _count),

    # 41. "how many meetings do I have this week"
    (re.compile(rf"how many (?P<entity>events?|meetings?|appointments?|reminders?|tasks?) do i have {_DATE_REF_SIMPLE}", re.I),
     "count_query", _count),

    # 42. "how many reminders" (no date → today)
    (re.compile(r"how many (?P<entity>events?|meetings?|appointments?|reminders?|tasks?|todos?|contacts?)", re.I),
     "count_query", lambda m: {"entity": m.group("entity").strip().lower(), "date_ref": "today"}),

    # 43. "number of events today"
    (re.compile(rf"(?:number|count|total) of (?P<entity>events?|meetings?|reminders?|tasks?|contacts?) {_DATE_REF_SIMPLE}", re.I),
     "count_query", _count),

    # ══════════════════════════════════════════════════════════════════════
    # RECENT — Latest items
    # ══════════════════════════════════════════════════════════════════════

    # 44. "recent reminders"
    (re.compile(r"(?:recent|latest|newest|last few) (?P<entity>reminders?|events?|meetings?|tasks?|contacts?)", re.I),
     "recent_query", _recent),

    # 45. "show me recent events"
    (re.compile(r"(?:show|list|get)(?: me)? (?:the )?(?:recent|latest|newest) (?P<entity>reminders?|events?|meetings?|tasks?|contacts?)", re.I),
     "recent_query", _recent),

    # 46. "what happened recently"
    (re.compile(r"what (?:happened|occurred|was there) recently", re.I),
     "recent_query", lambda _: {"entity": "events"}),

    # ══════════════════════════════════════════════════════════════════════
    # CALENDAR — Additional informal patterns
    # ══════════════════════════════════════════════════════════════════════

    # 47. "am I free today/tomorrow"
    (re.compile(rf"am i (?:free|available|busy) {_DATE_REF_SIMPLE}", re.I),
     "calendar_range", _date_ref),

    # 48. "what time is my next meeting"
    (re.compile(r"what time is (?:my )?next (?:meeting|event|appointment)", re.I),
     "calendar_range", lambda _: {"date_ref": "today"}),

    # 49. "next meeting"
    (re.compile(r"(?:my )?next (?:meeting|event|appointment)", re.I),
     "calendar_range", lambda _: {"date_ref": "today"}),

    # 50. "calendar overview"
    (re.compile(r"(?:calendar|schedule|agenda) (?:overview|summary)", re.I),
     "calendar_range", lambda _: {"date_ref": "this week"}),

    # 51. "free slots tomorrow"
    (re.compile(rf"(?:free|available|open) (?:slots?|times?) {_DATE_REF_SIMPLE}", re.I),
     "calendar_range", _date_ref),

    # 52. "what's left today"
    (re.compile(r"what(?:'s| is) left (?P<date_ref>today|this week)", re.I),
     "reminders_range", _date_ref),

    # 53. "anything due this week"
    (re.compile(rf"anything (?:due|coming up) {_DATE_REF_SIMPLE}", re.I),
     "reminders_range", _date_ref),

    # ══════════════════════════════════════════════════════════════════════
    # PHOTOS
    # ══════════════════════════════════════════════════════════════════════

    # photo_date: "photos from last week" / "photo from yesterday"
    # Restricted to refs that parse_date_reference handles. "last month"/"this month"/year
    # are excluded because parse_date_reference returns None for them, causing silent
    # degradation to an unfiltered search.
    (re.compile(
        r"photos?\s+from\s+(?P<date_ref>yesterday|today|last week|this week)\b",
        re.I,
    ), "photo_date", _photo_date),

    # photo_location: "photos in Paris" / "photos near home" / "photos from Tokyo"
    (re.compile(r"photos?\s+(?:in|from|near|at)\s+(?P<location>.+)", re.I),
     "photo_location", _photo_location),

    # photo_camera: "photos with iPhone" / "photos taken with Canon"
    # 'from' intentionally excluded — it conflicts with photo_location above.
    (re.compile(
        r"photos?\s+(?:with|taken with|shot with)\s+(?P<camera>.+?)(?:\s+camera|\s+phone|\s+iphone)?\s*$",
        re.I,
    ), "photo_camera", _photo_camera),
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
