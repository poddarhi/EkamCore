"""PLA follow-up suggestion workflow (S14-006 / ART-13 §7 row 1).

Daily workflow: identify trusted persons who may need follow-up.

Algorithm:
  1. Load all trusted persons via ``context.get_persons``.
  2. For each person, load their graph edges and compute the last
     interaction date (max ``created_at`` among ``appears_in`` and
     ``attended`` edges).
  3. Skip persons with no interaction data, recent interactions
     (within the lookback window), or an upcoming event in the
     next 7 days.
  4. Score = days_since / lookback (higher = more overdue).
  5. Sort descending, take the top ``max_suggestions`` entries.
  6. For each, check dedup (existing un-acknowledged card for
     today) and snooze (snoozed card with future ``snoozed_until``).
  7. Produce a ``follow_up_suggestion`` card.

No LLM call — purely deterministic. This keeps the workflow fast
and saves LLM quota for the weekly summary.

The workflow is invoked by ``PackRunner`` via the "daily" key in
the workflow dispatch map. It receives a fully-gated
``PackContext`` — all data access goes through capability-checked
methods.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog

from api.services.pack.pack_context import PackContext

logger = structlog.get_logger()

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_MAX_SUGGESTIONS = 5
UPCOMING_EVENT_HORIZON_DAYS = 7


async def run_follow_up_suggestions(context: PackContext) -> None:
    """Entry point called by PackRunner for pack_id='pla', workflow='daily'."""
    today = date.today()
    now = datetime.now(timezone.utc)

    try:
        persons = await context.get_persons(limit=200)
    except Exception:
        logger.info(
            "pla_follow_up_no_persons",
            reason="get_persons failed or consent off",
        )
        return

    if not persons:
        return

    lookback_days = DEFAULT_LOOKBACK_DAYS
    max_suggestions = DEFAULT_MAX_SUGGESTIONS

    scored: list[dict[str, Any]] = []

    for person in persons:
        try:
            edges = await context.get_edges_for_person(person.id)
        except Exception:
            continue

        interaction_edges = [
            e
            for e in edges
            if e.edge_type in ("appears_in", "attended")
        ]
        if not interaction_edges:
            continue

        last_date = max(e.created_at for e in interaction_edges)
        if last_date.tzinfo is None:
            last_date = last_date.replace(tzinfo=timezone.utc)
        days_since = (now - last_date).days
        if days_since < lookback_days:
            continue

        # Skip if upcoming event in the next 7 days.
        try:
            upcoming = await context.get_events_in_range(
                start=now,
                end=now + timedelta(days=UPCOMING_EVENT_HORIZON_DAYS),
                limit=50,
            )
            has_upcoming = _person_in_events(person, upcoming)
        except Exception:
            has_upcoming = False

        if has_upcoming:
            continue

        priority = round(days_since / max(lookback_days, 1), 2)
        last_edge = max(interaction_edges, key=lambda e: e.created_at)

        scored.append(
            {
                "person": person,
                "days_since": days_since,
                "priority": priority,
                "last_edge": last_edge,
            }
        )

    scored.sort(key=lambda x: x["priority"], reverse=True)
    candidates = scored[:max_suggestions]

    produced = 0
    for entry in candidates:
        person = entry["person"]
        last_edge = entry["last_edge"]

        try:
            if await context.has_pending_card_for_person(
                person.id, "follow_up_suggestion", today
            ):
                continue
            if await context.is_person_snoozed(
                person.id, "follow_up_suggestion"
            ):
                continue
        except Exception:
            pass

        interaction_type = (
            "event" if last_edge.edge_type == "attended" else "photo"
        )

        await context.produce_card(
            "follow_up_suggestion",
            {
                "person_id": str(person.id),
                "person_display_name": person.display_name,
                "days_since_last_interaction": entry["days_since"],
                "last_interaction_type": interaction_type,
                "last_interaction_context": "",
                "priority": entry["priority"],
            },
        )
        produced += 1

    logger.info(
        "pla_follow_up_produced",
        workspace_id=str(context.workspace_id),
        candidates=len(scored),
        produced=produced,
    )


def _person_in_events(person, events) -> bool:
    """Quick check: does the person's display_name appear in any
    of the event participant lists? Mirrors the attendance matching
    used by ``GraphEdgeBuilder.build_person_event_edges``."""
    name = (person.display_name or "").lower()
    if not name:
        return False
    for ev in events:
        participants = ev.participants_json or []
        for p in participants:
            if isinstance(p, str) and name in p.lower():
                return True
            if isinstance(p, dict):
                for val in p.values():
                    if isinstance(val, str) and name in val.lower():
                        return True
    return False
