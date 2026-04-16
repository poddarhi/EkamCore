"""PLA weekly summary workflow (S14-007 / ART-13 §7 row 2).

Weekly workflow: compile a week of interactions into structured
stats, feed them to the local LLM via ``PackContext.ask_llm``,
parse a 2-4 sentence summary, and produce a ``weekly_summary``
card. When the LLM is down, over-quota, or returns gibberish,
the workflow falls back to a template-based summary so the user
*always* sees a card.

LLM usage: exactly **1 call** per run. The prompt extends
``recap_summary_v1``'s system preamble with people-specific
signals (top persons, interaction counts). Temperature 0.3 for
deterministic-ish prose; max_tokens 300 to stay well within a
single Ollama round-trip.

The workflow uses ``ask_llm`` (single-prompt string) rather than
the multi-message LLM client directly, because ``ask_llm`` is
the only LLM surface ``PackContext`` exposes.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog

from api.services.pack.pack_context import PackContext

logger = structlog.get_logger()


def _week_range(reference: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week containing ``reference``.

    If ``reference`` is Monday, the range covers *this* week up to
    now (Monday→Sunday); otherwise it covers the *previous* week.
    """
    weekday = reference.weekday()  # 0=Mon
    monday = reference - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _build_prompt(stats: dict[str, Any]) -> str:
    """Assemble the single-string prompt for ``ask_llm``.

    Embeds the system instruction and the structured data in one
    block because ``ask_llm`` takes a flat prompt, not a message
    list. The prompt shape mirrors ``recap_summary_v1`` extended
    with people signals.
    """
    top_lines = []
    for p in stats.get("top_persons", [])[:5]:
        top_lines.append(
            f"  - {p['name']}: {p['interaction_count']} interactions"
        )

    parts = [
        "You are a personal assistant summarizing a user's week.",
        "Generate a natural, concise summary (2-4 sentences) from the data below.",
        "Focus on: people seen, key meetings, photos, reminders.",
        'Tone: friendly, first-person ("You had...").',
        "Use first names when referring to people.",
        "NEVER invent events or details not in the data.",
        "",
        'Output ONLY valid JSON: {"summary": "Your 2-4 sentence recap."}',
        "",
        f"Period: weekly ({stats['week_start']} to {stats['week_end']})",
        f"Events attended: {stats['events_count']}",
        f"People seen: {stats['persons_seen']}",
        f"Reminders completed: {stats['reminders_completed']}",
        f"New photos: {stats['new_photos']}",
        f"New files: {stats['new_files']}",
    ]
    if top_lines:
        parts.append("Top people:")
        parts.extend(top_lines)

    return "\n".join(parts)


def _fallback_summary(stats: dict[str, Any]) -> str:
    """Template-based summary when the LLM is unavailable.

    Always produces a readable sentence so the user still gets a
    card even if Ollama is down or over-quota.
    """
    persons_seen = stats.get("persons_seen", 0)
    events = stats.get("events_count", 0)
    photos = stats.get("new_photos", 0)

    parts: list[str] = []
    if events > 0 or persons_seen > 0:
        parts.append(
            f"This week you attended {events} events and "
            f"saw {persons_seen} people."
        )
    else:
        parts.append("It was a quiet week.")

    top = stats.get("top_persons", [])
    if top:
        names = ", ".join(p["name"] for p in top[:3])
        parts.append(f"Top connections: {names}.")

    if photos > 0:
        parts.append(f"{photos} new photos were added.")

    return " ".join(parts)


def _parse_llm_response(raw: str) -> str | None:
    """Try to extract the ``summary`` field from the LLM's JSON
    response. Returns ``None`` on any parse failure so the caller
    can fall back to the template.
    """
    try:
        # The LLM sometimes wraps the JSON in markdown fences.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )
        data = json.loads(cleaned)
        summary = data.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return None


async def run_weekly_summary(context: PackContext) -> None:
    """Entry point called by PackRunner for pack_id='pla', workflow='weekly'."""
    today = date.today()
    week_start, week_end = _week_range(today)

    # Dedup: one weekly_summary per target week.
    try:
        if await context.has_pending_card_for_person(
            context.workspace_id,  # abuse person_id slot with ws for dedup key
            "weekly_summary",
            week_start,
        ):
            logger.info(
                "pla_weekly_summary_dedup",
                workspace_id=str(context.workspace_id),
            )
            return
    except Exception:
        pass  # if dedup check fails, produce a new card anyway

    # ── Gather structured data ─────────────────────────────────────

    start_dt = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(week_end, datetime.max.time(), tzinfo=timezone.utc)

    try:
        events = await context.get_events_in_range(start=start_dt, end=end_dt)
    except Exception:
        events = []

    try:
        persons = await context.get_persons(limit=200)
    except Exception:
        persons = []

    # Per-person interaction count for the week.
    person_interaction_counts: dict[str, int] = {}
    for person in persons:
        try:
            edges = await context.get_edges_for_person(person.id, limit=200)
        except Exception:
            edges = []
        week_edges = [
            e
            for e in edges
            if e.edge_type in ("appears_in", "attended")
            and e.created_at >= start_dt
        ]
        if week_edges:
            person_interaction_counts[str(person.id)] = len(week_edges)

    try:
        reminders = await context.get_reminders(limit=500)
    except Exception:
        reminders = []
    reminders_completed = sum(
        1
        for r in reminders
        if getattr(r, "completed_at", None)
        and r.completed_at >= start_dt
    )

    try:
        photos = await context.get_photos(limit=500)
    except Exception:
        photos = []
    new_photos = sum(
        1
        for p in photos
        if getattr(p, "created_at", None) and p.created_at >= start_dt
    )

    try:
        files = await context.get_files(limit=500)
    except Exception:
        files = []
    new_files = sum(
        1
        for f in files
        if getattr(f, "created_at", None) and f.created_at >= start_dt
    )

    # Top persons by interaction count.
    top_persons: list[dict[str, Any]] = []
    person_map = {str(p.id): p for p in persons}
    for pid, count in sorted(
        person_interaction_counts.items(), key=lambda x: x[1], reverse=True
    )[:5]:
        p = person_map.get(pid)
        if p:
            top_persons.append(
                {
                    "name": p.display_name,
                    "person_id": str(p.id),
                    "interaction_count": count,
                }
            )

    stats: dict[str, Any] = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "events_count": len(events),
        "persons_seen": len(person_interaction_counts),
        "reminders_completed": reminders_completed,
        "new_photos": new_photos,
        "new_files": new_files,
        "top_persons": top_persons,
    }

    # ── LLM call with graceful degradation ─────────────────────────

    llm_generated = False
    summary_text = _fallback_summary(stats)

    try:
        prompt = _build_prompt(stats)
        raw = await context.ask_llm(prompt, max_tokens=300, temperature=0.3)
        parsed = _parse_llm_response(raw)
        if parsed:
            summary_text = parsed
            llm_generated = True
        else:
            logger.info(
                "pla_weekly_summary_llm_parse_failed",
                workspace_id=str(context.workspace_id),
            )
    except Exception:
        logger.info(
            "pla_weekly_summary_llm_unavailable",
            workspace_id=str(context.workspace_id),
        )

    # ── Produce card ───────────────────────────────────────────────

    await context.produce_card(
        "weekly_summary",
        {
            "summary_text": summary_text,
            "week_start": stats["week_start"],
            "week_end": stats["week_end"],
            "stats": {
                "events_count": stats["events_count"],
                "persons_seen": stats["persons_seen"],
                "reminders_completed": stats["reminders_completed"],
                "new_files": stats["new_files"],
                "new_photos": stats["new_photos"],
            },
            "top_persons": top_persons,
            "llm_generated": llm_generated,
        },
    )

    logger.info(
        "pla_weekly_summary_produced",
        workspace_id=str(context.workspace_id),
        llm_generated=llm_generated,
        persons_seen=stats["persons_seen"],
        events=stats["events_count"],
    )
