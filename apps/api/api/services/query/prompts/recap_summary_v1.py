"""Recap summary prompt template (G-04 / ART-12 Section 7).

Generates a 2-4 sentence natural language recap from structured data.
Model: llama3.1:8b | Temperature: 0.3 | Timeout: 10s
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a personal assistant summarizing a user's day or week.\n"
    "Generate a natural, concise summary (2-4 sentences) from the data below.\n"
    "Focus on: key meetings, urgent reminders, newly ingested documents.\n"
    "Tone: friendly, professional, first-person (\"You had...\").\n"
    "NEVER invent events or details not in the data.\n\n"
    "Output ONLY valid JSON with no markdown, no code fences, no preamble:\n"
    '{"summary": "Your 2-4 sentence recap here."}'
)

MODEL = "llama3.1:8b"
TEMPERATURE = 0.3
TIMEOUT_S = 10.0


def build_messages(
    period: str,
    event_count: int,
    reminder_count: int,
    file_count: int,
    highlights: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build the messages list for recap summarization.

    Args:
        period:         "daily" or "weekly".
        event_count:    Number of calendar events in the period.
        reminder_count: Number of reminders (due or completed).
        file_count:     Number of newly ingested files.
        highlights:     Optional list of notable items (event titles, etc.).

    Returns:
        Two-element list: [system_message, user_message].
    """
    parts = [
        f"Period: {period}",
        f"Events: {event_count}",
        f"Reminders: {reminder_count}",
        f"New documents: {file_count}",
    ]
    if highlights:
        parts.append("Highlights: " + ", ".join(highlights[:10]))

    user_content = "\n".join(parts)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
