"""PLA relationship reminder workflow (S14-008 / ART-13 §7 row 3).

Daily workflow: identify trusted persons with **strong** graph
connections (avg edge strength >= 0.5) who have gone cold
(no interaction in ``pla.relationship_inactive_days``, default 30).

Distinct from follow-up suggestions:
  - Follow-ups fire after the short lookback (7 days) for any
    person regardless of connection strength.
  - Relationship reminders fire after the longer inactive threshold
    (30 days) only for strong connections.
  - A person who already received a follow-up card today is
    skipped to avoid double-nagging.

No LLM call — deterministic.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog

from api.services.pack.pack_context import PackContext

logger = structlog.get_logger()

STRENGTH_THRESHOLD = 0.5
DEFAULT_INACTIVE_DAYS = 30
DEFAULT_MAX_SUGGESTIONS = 5


def _relationship_context(edges) -> str:
    """Generate a short human-readable context string from the
    edge type distribution."""
    types: dict[str, int] = {}
    for e in edges:
        types[e.edge_type] = types.get(e.edge_type, 0) + 1

    total = sum(types.values()) or 1
    dominant = max(types, key=types.get, default="")  # type: ignore[arg-type]

    if dominant == "appears_in" and types.get("appears_in", 0) / total > 0.6:
        return "Many shared photos"
    if dominant == "attended" and types.get("attended", 0) / total > 0.6:
        return "Frequent at events together"
    if "associated_with" in types:
        return "Collaborated on documents"
    return "Active in your network"


async def run_relationship_reminders(context: PackContext) -> None:
    """Entry point — runs after follow-up suggestions in the composite
    daily workflow."""
    today = date.today()
    now = datetime.now(timezone.utc)

    try:
        persons = await context.get_persons(limit=200)
    except Exception:
        logger.info(
            "pla_relationship_no_persons",
            reason="get_persons failed or consent off",
        )
        return

    if not persons:
        return

    inactive_days = DEFAULT_INACTIVE_DAYS
    max_suggestions = DEFAULT_MAX_SUGGESTIONS

    scored: list[dict[str, Any]] = []

    for person in persons:
        try:
            edges = await context.get_edges_for_person(person.id)
        except Exception:
            continue

        if not edges:
            continue

        strengths = [e.strength for e in edges if hasattr(e, "strength")]
        avg_strength = sum(strengths) / len(strengths) if strengths else 0.0
        if avg_strength < STRENGTH_THRESHOLD:
            continue

        interaction_edges = [
            e for e in edges if e.edge_type in ("appears_in", "attended")
        ]
        if not interaction_edges:
            continue

        last_date = max(e.created_at for e in interaction_edges)
        if last_date.tzinfo is None:
            last_date = last_date.replace(tzinfo=timezone.utc)
        days_since = (now - last_date).days
        if days_since < inactive_days:
            continue

        urgency = round(avg_strength * (days_since / max(inactive_days, 1)), 2)

        scored.append(
            {
                "person": person,
                "days_since": days_since,
                "avg_strength": round(avg_strength, 2),
                "urgency": urgency,
                "edges": edges,
            }
        )

    scored.sort(key=lambda x: x["urgency"], reverse=True)
    candidates = scored[:max_suggestions]

    produced = 0
    for entry in candidates:
        person = entry["person"]

        try:
            # Skip if already has a follow-up suggestion today.
            if await context.has_pending_card_for_person(
                person.id, "follow_up_suggestion", today
            ):
                continue
            # Skip if already has a relationship reminder today.
            if await context.has_pending_card_for_person(
                person.id, "relationship_reminder", today
            ):
                continue
            if await context.is_person_snoozed(
                person.id, "relationship_reminder"
            ):
                continue
        except Exception:
            pass

        context_text = _relationship_context(entry["edges"])

        await context.produce_card(
            "relationship_reminder",
            {
                "person_id": str(person.id),
                "person_display_name": person.display_name,
                "days_since_last_interaction": entry["days_since"],
                "graph_strength": entry["avg_strength"],
                "relationship_context": context_text,
            },
        )
        produced += 1

    logger.info(
        "pla_relationship_reminders_produced",
        workspace_id=str(context.workspace_id),
        candidates=len(scored),
        produced=produced,
    )
