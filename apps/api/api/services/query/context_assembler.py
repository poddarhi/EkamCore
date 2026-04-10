"""Context assembler for LLM grounded QA (S09-001).

Converts a list of search-result Cards into a plain-text context block suitable
for inclusion in an LLM prompt.  The context is trimmed to MAX_CONTEXT_CHARS
(~3000 tokens) so it fits within phi3:mini's 4096-token window alongside the
system prompt and question.
"""

from __future__ import annotations

from api.schemas.envelope import Card

MAX_CONTEXT_CHARS = 12_000  # ~3000 tokens (4 chars ≈ 1 token)


def _format_card(card: Card) -> tuple[str, str]:
    """Format a single card into a context snippet and its source title.

    Returns:
        (formatted_text, source_title) — both empty strings if the card type
        is not handled (e.g. StatusCard, PackCard).
    """
    p = card.payload
    ctype = card.type  # type: ignore[union-attr]

    if ctype == "event":
        title = p.get("title") or "Untitled event"
        start = p.get("start_at", "")
        location = p.get("location")
        loc_str = f" at {location}" if location else ""
        return (f"[Event: {title}]\n{start}{loc_str}", title)

    if ctype == "reminder":
        title = p.get("title") or "Untitled reminder"
        due = p.get("due_at")
        priority = p.get("priority") or "none"
        due_str = f"\nDue: {due}" if due else ""
        return (f"[Reminder: {title}]{due_str}\nPriority: {priority}", title)

    if ctype == "file":
        filename = p.get("filename") or p.get("path") or "document"
        snippet = p.get("snippet") or p.get("path") or ""
        body = f"\n{snippet}" if snippet else ""
        return (f"[Document: {filename}]{body}", filename)

    if ctype == "photo":
        taken_at = p.get("taken_at", "")
        location = p.get("location_name") or ""
        title = f"Photo {taken_at}" if taken_at else "Photo"
        loc_str = f"\nLocation: {location}" if location else ""
        return (f"[Photo: {taken_at}]{loc_str}", title)

    if ctype == "person":
        name = p.get("display_name") or p.get("name") or "Contact"
        org = p.get("organization")
        org_str = f"\nOrganization: {org}" if org else ""
        return (f"[Contact: {name}]{org_str}", name)

    return ("", "")


def assemble_context(cards: list[Card]) -> tuple[str, list[str]]:
    """Format cards into a single context string for the LLM.

    Cards are included in order of priority_score (assumed pre-sorted by
    the search layer) until the character budget is exhausted.

    Args:
        cards: Search result cards from ``search_all()``.

    Returns:
        (context_text, source_titles) — context_text is the formatted block
        ready for insertion into the prompt; source_titles is the list of
        labels used, in the same order, for hallucination validation.
    """
    parts: list[str] = []
    titles: list[str] = []
    total = 0

    for card in cards:
        text, title = _format_card(card)
        if not text:
            continue
        if total + len(text) > MAX_CONTEXT_CHARS:
            break
        parts.append(text)
        titles.append(title)
        total += len(text)

    return "\n\n".join(parts), titles
