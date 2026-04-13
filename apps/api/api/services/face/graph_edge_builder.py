"""Populate graph_edges for Person ↔ Photo / Event / File (S12-007).

Graph edges are a read-optimised denormalization. Face clusters,
calendar attendance, and paperless correspondents are already stored
in their own tables — edges give us a single place to answer
questions like "show every photo + event + file associated with
Alice" in O(1) hops.

Design rules:

  1. **Idempotent by scope.** Every builder first *deletes* the
     edges it owns (``from_type='trusted_person'`` + a fixed
     ``edge_type``) for the persons in scope, then re-inserts.
     Callers get a clean rebuild per invocation — no stale edges
     survive. Deletion + insertion are in the same transaction.

  2. **Workspace isolation.** Every query and every inserted row
     scopes on ``workspace_id``. Attempting to bridge across
     workspaces is physically impossible from the SELECT side
     because the joins stay workspace-bound.

  3. **Cheap per-person hooks.** ``build_person_photo_edges``
     accepts an optional ``person_ids`` filter so mutation hooks
     (create_from_cluster / merge / split) rebuild only the
     affected persons, not the whole workspace.

  4. **PII-safe logging.** Counts and ids only. Never display_name,
     never email, never photo bytes.

Edge vocabulary:
  - ``trusted_person`` → ``photo_asset``  : ``appears_in``
  - ``trusted_person`` → ``calendar_event``: ``attended``
  - ``trusted_person`` → ``file``          : ``associated_with``
"""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.graph_edge import GraphEdge
from api.db.models.photo_asset import PhotoAsset
from api.db.models.trusted_person import TrustedPerson

logger = structlog.get_logger()


NAME_FUZZY_THRESHOLD = 0.85


class EdgeReport(BaseModel):
    photo_edges: int = 0
    event_edges: int = 0
    file_edges: int = 0
    duration_ms: int = 0


# ── Person → photo_asset ───────────────────────────────────────────────────


async def build_person_photo_edges(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    person_ids: list[UUID] | None = None,
) -> int:
    """Rebuild the ``appears_in`` edge set for one or more persons.

    When ``person_ids`` is None, every non-deleted person in the
    workspace is rebuilt. Returns the total number of edges written.
    """
    person_stmt = select(TrustedPerson.id).where(
        and_(
            TrustedPerson.workspace_id == workspace_id,
            TrustedPerson.deleted_at.is_(None),
        )
    )
    if person_ids is not None:
        person_stmt = person_stmt.where(TrustedPerson.id.in_(list(person_ids)))
    persons = (await db.execute(person_stmt)).scalars().all()
    if not persons:
        return 0

    # Delete any existing appears_in edges owned by these persons so the
    # rebuild is a clean slate and idempotent.
    await db.execute(
        delete(GraphEdge).where(
            and_(
                GraphEdge.workspace_id == workspace_id,
                GraphEdge.from_type == "trusted_person",
                GraphEdge.from_id.in_(list(persons)),
                GraphEdge.to_type == "photo_asset",
                GraphEdge.edge_type == "appears_in",
            )
        )
    )
    await db.flush()

    written = 0
    for person_id in persons:
        rows = (
            await db.execute(
                select(
                    FaceDetection.photo_asset_id,
                    FaceCluster.id.label("cluster_id"),
                )
                .join(FaceCluster, FaceCluster.id == FaceDetection.cluster_id)
                .where(
                    and_(
                        FaceCluster.trusted_person_id == person_id,
                        FaceCluster.workspace_id == workspace_id,
                        FaceDetection.workspace_id == workspace_id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        ).all()
        if not rows:
            continue
        # Collapse to one edge per distinct photo_asset. The evidence
        # blob records the contributing cluster ids and the face count.
        by_photo: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {"cluster_ids": set(), "face_count": 0}
        )
        for r in rows:
            entry = by_photo[r.photo_asset_id]
            entry["cluster_ids"].add(str(r.cluster_id))
            entry["face_count"] += 1

        for photo_id, entry in by_photo.items():
            strength = min(1.0, float(entry["face_count"]) / 3.0)
            db.add(
                GraphEdge(
                    workspace_id=workspace_id,
                    from_type="trusted_person",
                    from_id=person_id,
                    to_type="photo_asset",
                    to_id=photo_id,
                    edge_type="appears_in",
                    evidence_json={
                        "cluster_ids": sorted(entry["cluster_ids"]),
                        "face_count": entry["face_count"],
                    },
                    strength=strength,
                )
            )
            written += 1
    await db.flush()
    logger.info(
        "person_photo_edges_built",
        workspace_id=str(workspace_id),
        person_count=len(persons),
        edges_written=written,
    )
    return written


# ── Person → calendar_event ───────────────────────────────────────────────


def _name_matches(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= NAME_FUZZY_THRESHOLD


def _extract_participant_key(participant: Any) -> tuple[str | None, str | None]:
    if isinstance(participant, str):
        if "@" in participant:
            return (participant.strip().lower(), None)
        return (None, participant.strip())
    if isinstance(participant, dict):
        email = (
            participant.get("email")
            or participant.get("address")
            or participant.get("mail")
        )
        name = (
            participant.get("name")
            or participant.get("display_name")
            or participant.get("displayName")
        )
        if isinstance(email, str):
            email = email.strip().lower()
        else:
            email = None
        if not isinstance(name, str):
            name = None
        return (email, name)
    return (None, None)


async def build_person_event_edges(
    *,
    workspace_id: UUID,
    db: AsyncSession,
) -> int:
    """Rebuild ``attended`` edges from persons to calendar events.

    Only persons with a ``canonical_contact_id`` participate — a
    cluster without a linked contact has no evidence for calendar
    attendance.
    """
    persons = (
        (
            await db.execute(
                select(TrustedPerson).where(
                    and_(
                        TrustedPerson.workspace_id == workspace_id,
                        TrustedPerson.deleted_at.is_(None),
                        TrustedPerson.canonical_contact_id.is_not(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if not persons:
        return 0

    # Wipe prior attended edges for these persons.
    await db.execute(
        delete(GraphEdge).where(
            and_(
                GraphEdge.workspace_id == workspace_id,
                GraphEdge.from_type == "trusted_person",
                GraphEdge.from_id.in_([p.id for p in persons]),
                GraphEdge.to_type == "calendar_event",
                GraphEdge.edge_type == "attended",
            )
        )
    )
    await db.flush()

    contacts = (
        (
            await db.execute(
                select(Contact).where(
                    and_(
                        Contact.workspace_id == workspace_id,
                        Contact.id.in_(
                            [p.canonical_contact_id for p in persons]
                        ),
                        Contact.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    contacts_by_id = {c.id: c for c in contacts}

    events = (
        (
            await db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.workspace_id == workspace_id
                )
            )
        )
        .scalars()
        .all()
    )

    written = 0
    for person in persons:
        contact = contacts_by_id.get(person.canonical_contact_id)
        if contact is None:
            continue
        contact_emails = set()
        for entry in contact.emails_json or []:
            if isinstance(entry, dict):
                raw = entry.get("address") or entry.get("email") or entry.get("value")
            elif isinstance(entry, str):
                raw = entry
            else:
                raw = None
            if isinstance(raw, str) and raw:
                contact_emails.add(raw.lower())
        contact_name = contact.display_name or " ".join(
            p for p in (contact.first_name, contact.last_name) if p
        ).strip()

        for ev in events:
            participants = ev.participants_json or []
            matched = False
            for p in participants:
                email, name = _extract_participant_key(p)
                if email and email in contact_emails:
                    matched = True
                    break
                if name and _name_matches(name, contact_name):
                    matched = True
                    break
            if not matched:
                continue
            db.add(
                GraphEdge(
                    workspace_id=workspace_id,
                    from_type="trusted_person",
                    from_id=person.id,
                    to_type="calendar_event",
                    to_id=ev.id,
                    edge_type="attended",
                    evidence_json={"match": "participant"},
                    strength=1.0,
                )
            )
            written += 1
    await db.flush()
    logger.info(
        "person_event_edges_built",
        workspace_id=str(workspace_id),
        person_count=len(persons),
        edges_written=written,
    )
    return written


# ── Person → file (via paperless correspondent bridge) ────────────────────


async def build_person_file_edges(
    *,
    workspace_id: UUID,
    db: AsyncSession,
) -> int:
    """Rebuild ``associated_with`` edges from persons to files.

    The bridge is: trusted_person.canonical_contact_id → (contact is
    linked to a paperless correspondent via S07-004's
    ``correspondent_candidate`` table) → files tagged with that
    correspondent. The linkage table does not yet expose a direct
    contact → file path in v1.0, so this builder is a no-op placeholder
    that safely returns 0. The test suite asserts it does not write
    anything rather than a specific count.
    """
    persons = (
        (
            await db.execute(
                select(TrustedPerson.id).where(
                    and_(
                        TrustedPerson.workspace_id == workspace_id,
                        TrustedPerson.deleted_at.is_(None),
                        TrustedPerson.canonical_contact_id.is_not(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if not persons:
        return 0
    await db.execute(
        delete(GraphEdge).where(
            and_(
                GraphEdge.workspace_id == workspace_id,
                GraphEdge.from_type == "trusted_person",
                GraphEdge.from_id.in_(list(persons)),
                GraphEdge.to_type == "file",
                GraphEdge.edge_type == "associated_with",
            )
        )
    )
    await db.flush()
    logger.info(
        "person_file_edges_built",
        workspace_id=str(workspace_id),
        person_count=len(persons),
        edges_written=0,
    )
    return 0


# ── Full rebuild ──────────────────────────────────────────────────────────


async def rebuild_all(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    scope: str = "all",
) -> EdgeReport:
    """Rebuild some or all person-sourced graph edges for a workspace.

    ``scope`` is one of ``photo``, ``event``, ``file``, or ``all``.
    Each builder is individually idempotent, so partial runs are safe.
    """
    import time

    t0 = time.monotonic()
    report = EdgeReport()
    if scope in ("photo", "all"):
        report.photo_edges = await build_person_photo_edges(
            workspace_id=workspace_id, db=db
        )
    if scope in ("event", "all"):
        report.event_edges = await build_person_event_edges(
            workspace_id=workspace_id, db=db
        )
    if scope in ("file", "all"):
        report.file_edges = await build_person_file_edges(
            workspace_id=workspace_id, db=db
        )
    report.duration_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "graph_rebuild_all",
        workspace_id=str(workspace_id),
        scope=scope,
        photo_edges=report.photo_edges,
        event_edges=report.event_edges,
        file_edges=report.file_edges,
        duration_ms=report.duration_ms,
    )
    return report
