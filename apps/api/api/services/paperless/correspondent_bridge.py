"""Paperless Correspondent → People Graph bridge (S07-004).

Maps Paperless correspondents to EkamCore contacts via fuzzy name matching,
creating candidate rows for future human review in the People Graph review
queue (S12-001).

Algorithm
─────────
For each correspondent pulled from Paperless:
  1. Build a normalised name string for every active contact in the workspace
     (display_name, or first_name + last_name if display_name is absent).
  2. Score each contact with difflib.SequenceMatcher — O(C) per correspondent,
     acceptable for the typical tens-to-hundreds of contacts per workspace.
  3. If the best score ≥ MATCH_THRESHOLD (0.6) → link that contact.
     Otherwise → record the correspondent with contact_id=NULL, score=0.
  4. Upsert into correspondent_contact_candidates.  Rows with status
     'confirmed' or 'rejected' are never overwritten — human decisions stick.

Idempotency
───────────
The UNIQUE constraint on (workspace_id, paperless_correspondent_id) plus the
status guard ensures re-running the bridge is always safe.

Privacy
───────
No correspondent names, contact names, or match details are emitted to logs —
only numeric counters.  Workspace/correlation IDs are fine.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.contact import Contact
from api.db.models.correspondent_candidate import (
    CANDIDATE_STATUS_CONFIRMED,
    CANDIDATE_STATUS_PENDING,
    CANDIDATE_STATUS_REJECTED,
    CorrespondentContactCandidate,
)
from api.services.paperless.client import get_paperless_client
from api.services.paperless.models import PaperlessCorrespondent

logger = structlog.get_logger()

MATCH_THRESHOLD: float = 0.6


@dataclass
class _ContactRecord:
    id: UUID
    name: str  # normalised, lower-cased for matching


def _normalise(raw: str) -> str:
    return " ".join(raw.casefold().split())


def _build_contact_records(contacts: list[Contact]) -> list[_ContactRecord]:
    records: list[_ContactRecord] = []
    for c in contacts:
        raw = c.display_name or f"{c.first_name or ''} {c.last_name or ''}".strip()
        if raw:
            records.append(_ContactRecord(id=c.id, name=_normalise(raw)))
    return records


def _best_match(
    correspondent_name: str,
    contact_records: list[_ContactRecord],
) -> tuple[UUID | None, float]:
    """Return (contact_id, score) for the best match, or (None, 0.0) if none qualifies."""
    if not contact_records:
        return None, 0.0

    query = _normalise(correspondent_name)
    best_id: UUID | None = None
    best_score: float = 0.0

    for record in contact_records:
        score = difflib.SequenceMatcher(None, query, record.name).ratio()
        if score > best_score:
            best_score = score
            best_id = record.id

    if best_score < MATCH_THRESHOLD:
        return None, best_score

    return best_id, best_score


async def run_correspondent_bridge(
    workspace_id: UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """Run the correspondent-to-contact bridge for one workspace.

    Returns a stats dict: {processed, new, updated, no_match}.

    Raises ServiceUnavailableError if Paperless is unreachable (caller logs).
    """
    client = get_paperless_client()

    # 1. Fetch correspondents from Paperless (raises on network / auth errors)
    correspondents: list[PaperlessCorrespondent] = await client.list_correspondents()

    if not correspondents:
        logger.info(
            "correspondent_bridge_no_correspondents",
            workspace_id=str(workspace_id),
        )
        return {"processed": 0, "new": 0, "updated": 0, "no_match": 0}

    # 2. Load active contacts for this workspace
    stmt = select(Contact).where(
        Contact.workspace_id == workspace_id,
        Contact.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    contacts = list(result.scalars().all())
    contact_records = _build_contact_records(contacts)

    # 3. Load existing candidates for workspace (to distinguish new vs updated)
    existing_stmt = select(CorrespondentContactCandidate).where(
        CorrespondentContactCandidate.workspace_id == workspace_id,
        CorrespondentContactCandidate.deleted_at.is_(None),
    )
    existing_result = await db.execute(existing_stmt)
    existing_map: dict[int, CorrespondentContactCandidate] = {
        row.paperless_correspondent_id: row
        for row in existing_result.scalars().all()
    }

    new_count = 0
    updated_count = 0
    no_match_count = 0

    now = datetime.now(timezone.utc)

    for corr in correspondents:
        contact_id, score = _best_match(corr.name, contact_records)
        if contact_id is None:
            no_match_count += 1

        existing = existing_map.get(corr.id)

        if existing is None:
            # INSERT
            candidate = CorrespondentContactCandidate(
                workspace_id=workspace_id,
                paperless_correspondent_id=corr.id,
                paperless_correspondent_name=corr.name,
                contact_id=contact_id,
                match_score=score,
                status=CANDIDATE_STATUS_PENDING,
            )
            db.add(candidate)
            new_count += 1
        else:
            # UPDATE only if not yet reviewed
            if existing.status in (CANDIDATE_STATUS_CONFIRMED, CANDIDATE_STATUS_REJECTED):
                continue
            existing.paperless_correspondent_name = corr.name
            existing.contact_id = contact_id
            existing.match_score = score
            existing.updated_at = now  # type: ignore[assignment]
            updated_count += 1

    await db.commit()

    logger.info(
        "correspondent_bridge_complete",
        workspace_id=str(workspace_id),
        processed=len(correspondents),
        new=new_count,
        updated=updated_count,
        no_match=no_match_count,
    )

    return {
        "processed": len(correspondents),
        "new": new_count,
        "updated": updated_count,
        "no_match": no_match_count,
    }
