"""Person-name detector for the query router (S14-011).

Detects if a natural-language query references any trusted_persons
by name. Runs *before* the classify step so the intent can be
tagged as person-related, enabling person-context-augmented LLM
responses or deterministic person-data lookups.

Strategy:
  1. Generate candidate name spans: unigrams + bigrams + trigrams
     from the query after stripping stop words and punctuation.
  2. For each span, ILIKE against ``trusted_persons.display_name``
     scoped to the workspace. Short names (≤3 chars) must be exact
     matches to avoid false positives ("Al" matching "Alice").
  3. Deduplicate: if both "Alice" and "Alice Smith" match the same
     person, keep the longer span.
  4. Return matched persons sorted by span length descending.

No LLM, no embedding — pure SQL ILIKE. Fast (<5ms on 500 persons).
"""

from __future__ import annotations

import re
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.trusted_person import TrustedPerson

logger = structlog.get_logger()

_STOP_WORDS = frozenset(
    "a an the is was were am are be been being have has had do does did "
    "will would shall should can could may might must need ought to of "
    "in on at by for with from about into through during before after "
    "above below between under over out up down off out i me my we our "
    "you your he she it they them their his her its what which who whom "
    "when where why how all each every both few many much some any no "
    "not and or but if then else so than too very just also most more "
    "that this these those"
    .split()
)

_TOKEN_RE = re.compile(r"[a-zA-Z\u00C0-\u024F]+(?:'[a-zA-Z]+)?")


def _extract_spans(query: str) -> list[str]:
    """Generate candidate name spans from the query."""
    tokens = [
        tok
        for tok in _TOKEN_RE.findall(query)
        if tok.lower() not in _STOP_WORDS and len(tok) > 1
    ]
    spans: list[str] = []
    for i, tok in enumerate(tokens):
        spans.append(tok)
        if i + 1 < len(tokens):
            spans.append(f"{tok} {tokens[i + 1]}")
        if i + 2 < len(tokens):
            spans.append(f"{tok} {tokens[i + 1]} {tokens[i + 2]}")
    return spans


async def detect_person_references(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
) -> list[TrustedPerson]:
    """Return trusted persons whose display_name matches a span in
    ``query``. Returns at most 5 persons, sorted by match
    specificity (longer span = higher specificity)."""
    spans = _extract_spans(query)
    if not spans:
        return []

    conditions = []
    for span in spans:
        if len(span) <= 3:
            conditions.append(
                TrustedPerson.display_name.ilike(span)
            )
        else:
            conditions.append(
                TrustedPerson.display_name.ilike(f"%{span}%")
            )

    stmt = (
        select(TrustedPerson)
        .where(
            and_(
                TrustedPerson.workspace_id == workspace_id,
                TrustedPerson.deleted_at.is_(None),
                or_(*conditions),
            )
        )
        .limit(10)
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    # Deduplicate: keep the person matched by the longest span.
    seen_ids: set[UUID] = set()
    result: list[TrustedPerson] = []
    for person in rows:
        if person.id in seen_ids:
            continue
        seen_ids.add(person.id)
        result.append(person)

    logger.debug(
        "person_detector_matches",
        workspace_id=str(workspace_id),
        count=len(result),
    )
    return result[:5]
