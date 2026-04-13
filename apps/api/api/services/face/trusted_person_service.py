"""TrustedPersonService — CRUD + cluster lifecycle actions (S12-004 / ART-11).

This service is the bridge between an unconfirmed face_cluster and a
confirmed trusted_person row. It owns:

  - listing / reading trusted persons for a workspace
  - creating a person from a cluster (manual label, or confirming a
    pre-ranked candidate from S12-003)
  - rejecting a cluster (reversible; S12-006 owns the undo path)
  - renaming and soft-deleting a trusted person

Design rules (each prevents a concrete bug class):

  1. **Workspace isolation.** Every SELECT, UPDATE and INSERT scopes
     on workspace_id. The endpoint layer derives workspace_id from
     the authenticated user, never from the request body or a path
     parameter, so a tampered client can't reach across workspaces.

  2. **Structured errors.** NotFoundError for missing rows,
     ValidationError for semantic request mistakes — never bare
     HTTPException, never a dict response. Error codes are the
     source of truth for the client-facing copy.

  3. **Audit everywhere.** Every mutation writes an object_audit_log
     row inside the caller's transaction so the audit and the
     state change commit atomically.

  4. **Soft delete only.** `delete` flips `trusted_persons.deleted_at`;
     the underlying face_cluster link is preserved so historical
     photo tags still resolve.

  5. **PII-safe logging.** Counts, ids, action names only. Never
     display_name, never email, never embeddings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.trusted_person import TrustedPerson
from api.errors import NotFoundError, ValidationError
from api.services import audit

logger = structlog.get_logger()


# ── Read paths ─────────────────────────────────────────────────────────────


async def list_persons(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[TrustedPerson], str | None]:
    """Cursor-paginated list of non-deleted trusted persons in a workspace.

    Ordered by ``created_at DESC, id DESC`` so "most recently confirmed
    first" is the natural default for the People Graph review UI. The
    cursor is the opaque stringified ``id`` of the last returned row;
    callers pass it back as ``cursor`` to fetch the next page.
    """
    stmt = (
        select(TrustedPerson)
        .where(
            and_(
                TrustedPerson.workspace_id == workspace_id,
                TrustedPerson.deleted_at.is_(None),
            )
        )
        .order_by(TrustedPerson.created_at.desc(), TrustedPerson.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        try:
            cursor_uuid = UUID(cursor)
        except ValueError as exc:
            raise ValidationError(
                error_code="VALIDATION_ERROR",
                message="Invalid cursor.",
            ) from exc
        stmt = stmt.where(TrustedPerson.id < cursor_uuid)
    rows = (await db.execute(stmt)).scalars().all()
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = str(rows[-1].id)
    return list(rows), next_cursor


async def get_person(
    *,
    person_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> TrustedPerson:
    row = (
        await db.execute(
            select(TrustedPerson).where(
                and_(
                    TrustedPerson.id == person_id,
                    TrustedPerson.workspace_id == workspace_id,
                    TrustedPerson.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(
            error_code="PERSON_NOT_FOUND",
            message="Trusted person not found.",
        )
    return row


# ── Mutations ──────────────────────────────────────────────────────────────


async def _load_cluster_for_update(
    db: AsyncSession, cluster_id: UUID, workspace_id: UUID
) -> FaceCluster:
    cluster = (
        await db.execute(
            select(FaceCluster).where(
                and_(
                    FaceCluster.id == cluster_id,
                    FaceCluster.workspace_id == workspace_id,
                    FaceCluster.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if cluster is None:
        raise NotFoundError(
            error_code="CLUSTER_NOT_FOUND",
            message="Face cluster not found.",
        )
    return cluster


async def create_from_cluster(
    *,
    cluster_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    display_name: str,
    canonical_contact_id: UUID | None = None,
    trust_source: str = "manual",
    db: AsyncSession,
    audit_action: str = "person_created_from_cluster",
    audit_metadata_extra: dict[str, Any] | None = None,
) -> TrustedPerson:
    """Create a trusted_person linked to ``cluster_id`` and mark the
    cluster as confirmed. Atomic with the caller's transaction.

    The caller is the router — `workspace_id` and `user_id` must come
    from the authenticated user, never from the request body.
    """
    cluster = await _load_cluster_for_update(db, cluster_id, workspace_id)

    if canonical_contact_id is not None:
        exists = (
            await db.execute(
                select(Contact.id).where(
                    and_(
                        Contact.id == canonical_contact_id,
                        Contact.workspace_id == workspace_id,
                        Contact.deleted_at.is_(None),
                    )
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            raise ValidationError(
                error_code="VALIDATION_ERROR",
                message="Canonical contact does not belong to this workspace.",
            )

    now = datetime.now(timezone.utc)
    person = TrustedPerson(
        workspace_id=workspace_id,
        display_name=display_name,
        canonical_contact_id=canonical_contact_id,
        trust_source=trust_source,
        confirmed_at=now,
        confirmed_by=user_id,
    )
    db.add(person)
    await db.flush()

    cluster.trusted_person_id = person.id
    cluster.cluster_state = "confirmed"
    await db.flush()

    metadata = {
        "cluster_id": str(cluster_id),
        "person_id": str(person.id),
        "trust_source": trust_source,
    }
    if canonical_contact_id is not None:
        metadata["canonical_contact_id"] = str(canonical_contact_id)
    if audit_metadata_extra:
        metadata.update(audit_metadata_extra)

    await audit.log_event(
        db=db,
        action=audit_action,
        object_type="trusted_persons",
        object_id=person.id,
        user_id=user_id,
        workspace_id=workspace_id,
        new_state={"trust_source": trust_source},
        metadata=metadata,
    )

    logger.info(
        "trusted_person_created",
        workspace_id=str(workspace_id),
        cluster_id=str(cluster_id),
        person_id=str(person.id),
        trust_source=trust_source,
    )
    return person


async def confirm_candidate(
    *,
    cluster_id: UUID,
    contact_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> TrustedPerson:
    """Confirm a pre-ranked candidate (from ``face_clusters.candidates_json``)
    as the identity of the cluster. Raises INVALID_CANDIDATE when the
    contact id is not in the cached candidate list.
    """
    cluster = await _load_cluster_for_update(db, cluster_id, workspace_id)

    candidates = cluster.candidates_json or []
    candidate_ids = {str(c.get("contact_id")) for c in candidates if isinstance(c, dict)}
    if str(contact_id) not in candidate_ids:
        raise ValidationError(
            error_code="INVALID_CANDIDATE",
            message="Contact is not one of this cluster's candidates.",
        )

    contact = (
        await db.execute(
            select(Contact).where(
                and_(
                    Contact.id == contact_id,
                    Contact.workspace_id == workspace_id,
                    Contact.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        raise NotFoundError(
            error_code="PERSON_NOT_FOUND",
            message="Candidate contact no longer exists.",
        )

    display_name = (
        contact.display_name
        or " ".join(
            part for part in (contact.first_name, contact.last_name) if part
        ).strip()
        or "Unknown"
    )

    return await create_from_cluster(
        cluster_id=cluster_id,
        workspace_id=workspace_id,
        user_id=user_id,
        display_name=display_name,
        canonical_contact_id=contact.id,
        trust_source="face_confirmed",
        db=db,
        audit_action="person_confirmed_from_candidate",
        audit_metadata_extra={"via": "candidate_confirmation"},
    )


async def reject_cluster(
    *,
    cluster_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    reason: str | None,
    db: AsyncSession,
) -> None:
    """Mark a cluster as rejected. Reversible via S12-006 undo.

    The cluster row and its member face_detections are left in place —
    rejection is a *state* not a deletion. Any existing
    ``trusted_person_id`` link is cleared so the cluster no longer
    resolves to that identity.
    """
    cluster = await _load_cluster_for_update(db, cluster_id, workspace_id)

    prior_state = cluster.cluster_state
    prior_person_id = cluster.trusted_person_id

    cluster.cluster_state = "rejected"
    cluster.trusted_person_id = None
    await db.flush()

    await audit.log_event(
        db=db,
        action="cluster_rejected",
        object_type="face_clusters",
        object_id=cluster_id,
        user_id=user_id,
        workspace_id=workspace_id,
        old_state={
            "cluster_state": prior_state,
            "trusted_person_id": str(prior_person_id) if prior_person_id else None,
        },
        new_state={"cluster_state": "rejected"},
        metadata={
            "cluster_id": str(cluster_id),
            "reason": reason,
        },
    )
    logger.info(
        "cluster_rejected",
        workspace_id=str(workspace_id),
        cluster_id=str(cluster_id),
    )


async def rename(
    *,
    person_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    new_name: str,
    db: AsyncSession,
) -> TrustedPerson:
    person = await get_person(
        person_id=person_id, workspace_id=workspace_id, db=db
    )
    old_name = person.display_name
    person.display_name = new_name
    await db.flush()
    await audit.log_event(
        db=db,
        action="person_renamed",
        object_type="trusted_persons",
        object_id=person_id,
        user_id=user_id,
        workspace_id=workspace_id,
        old_state={"display_name_present": bool(old_name)},
        new_state={"display_name_present": True},
        metadata={"person_id": str(person_id)},
    )
    logger.info(
        "trusted_person_renamed",
        workspace_id=str(workspace_id),
        person_id=str(person_id),
    )
    return person


async def delete(
    *,
    person_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> None:
    """Soft delete: set deleted_at=now(). The face_clusters link is
    preserved so historical tags resolve until the cluster itself is
    re-labelled or revoked via consent hard-delete."""
    person = await get_person(
        person_id=person_id, workspace_id=workspace_id, db=db
    )
    person.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await audit.log_event(
        db=db,
        action="person_deleted",
        object_type="trusted_persons",
        object_id=person_id,
        user_id=user_id,
        workspace_id=workspace_id,
        metadata={"person_id": str(person_id)},
    )
    logger.info(
        "trusted_person_deleted",
        workspace_id=str(workspace_id),
        person_id=str(person_id),
    )
