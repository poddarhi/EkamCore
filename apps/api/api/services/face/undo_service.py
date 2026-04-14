"""Undo operations on trusted persons (S12-006).

Applies a captured ``inverse_payload`` to reverse a prior merge,
split, rename, or delete. Undoing an undo is NOT supported for
v1.0 — a redo path requires distinct semantics (e.g. an editable
timeline) and is deliberately out of scope.

Public API:

  - ``list_recent_operations(workspace_id, limit)``
  - ``undo_last_operation(workspace_id, user_id, db)``
  - ``undo_specific_operation(operation_id, workspace_id, user_id, db)``

All mutations stamp ``undone_at`` + ``undone_by_user_id`` on the
underlying ``person_operations`` row so the history tab shows
which entries have been reversed without losing the row itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.graph_edge import GraphEdge
from api.db.models.person_operation import PersonOperation
from api.db.models.trusted_person import TrustedPerson
from api.errors import ConflictError, NotFoundError
from api.services import audit
from api.services.face.split_service import _compute_centroid_from_faces

logger = structlog.get_logger()


@dataclass
class OperationUndoResult:
    operation_id: UUID
    operation_type: str


# ── Queries ────────────────────────────────────────────────────────────────


async def list_recent_operations(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    limit: int = 50,
) -> list[PersonOperation]:
    rows = (
        (
            await db.execute(
                select(PersonOperation)
                .where(PersonOperation.workspace_id == workspace_id)
                .order_by(PersonOperation.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _load_operation(
    operation_id: UUID, workspace_id: UUID, db: AsyncSession
) -> PersonOperation:
    row = (
        await db.execute(
            select(PersonOperation).where(
                and_(
                    PersonOperation.id == operation_id,
                    PersonOperation.workspace_id == workspace_id,
                )
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(
            error_code="OPERATION_NOT_FOUND",
            message="Operation not found.",
        )
    return row


# ── Per-type inverse apply ────────────────────────────────────────────────


async def _apply_undo_merge(
    payload: dict[str, Any], workspace_id: UUID, db: AsyncSession
) -> None:
    keeper_id = UUID(payload["keeper_id"])
    keeper_merged_from_before = payload.get("keeper_merged_from_ids_before") or []
    restored_persons = payload.get("restored_persons") or []
    edge_rewrites = payload.get("edge_rewrites") or []
    edge_drops = payload.get("edge_drops") or []

    # Un-delete every non-keeper; restore their columns.
    for entry in restored_persons:
        p = (
            await db.execute(
                select(TrustedPerson).where(
                    TrustedPerson.id == UUID(entry["person_id"])
                )
            )
        ).scalar_one()
        p.deleted_at = None
        p.display_name = entry["display_name"]
        p.canonical_contact_id = (
            UUID(entry["canonical_contact_id"])
            if entry.get("canonical_contact_id")
            else None
        )
        p.trust_source = entry["trust_source"]
        p.confirmed_at = (
            datetime.fromisoformat(entry["confirmed_at"])
            if entry.get("confirmed_at")
            else None
        )
        p.confirmed_by = (
            UUID(entry["confirmed_by"])
            if entry.get("confirmed_by")
            else None
        )
        p.merged_from_ids = entry.get("merged_from_ids") or None

        for cid in entry.get("cluster_ids") or []:
            await db.execute(
                FaceCluster.__table__.update()
                .where(FaceCluster.id == UUID(cid))
                .values(trusted_person_id=p.id)
            )

    # Restore keeper's merged_from_ids.
    keeper = (
        await db.execute(
            select(TrustedPerson).where(TrustedPerson.id == keeper_id)
        )
    ).scalar_one()
    keeper.merged_from_ids = keeper_merged_from_before or None

    # Undo graph-edge rewrites: point them back at the original to_id.
    for rewrite in edge_rewrites:
        edge_id = UUID(rewrite["edge_id"])
        original_to_id = UUID(rewrite["original_to_id"])
        row = (
            await db.execute(select(GraphEdge).where(GraphEdge.id == edge_id))
        ).scalar_one_or_none()
        if row is not None:
            row.to_id = original_to_id

    # Recreate dropped edges.
    for drop in edge_drops:
        db.add(
            GraphEdge(
                workspace_id=workspace_id,
                from_type=drop["from_type"],
                from_id=UUID(drop["from_id"]),
                to_type=drop["to_type"],
                to_id=UUID(drop["to_id"]),
                edge_type=drop["edge_type"],
                strength=drop.get("strength", 1.0),
                evidence_json=drop.get("evidence_json"),
            )
        )
    await db.flush()


async def _apply_undo_split(
    payload: dict[str, Any], workspace_id: UUID, db: AsyncSession
) -> None:
    new_person_id = UUID(payload["new_person_id"])
    new_cluster_id = UUID(payload["new_cluster_id"])
    face_detection_restores = payload.get("face_detection_restores") or []

    # Restore each face_detection's original cluster_id.
    touched_cluster_ids: set[UUID] = set()
    for entry in face_detection_restores:
        fd_id = UUID(entry["face_detection_id"])
        original_cid = UUID(entry["cluster_id"])
        await db.execute(
            FaceDetection.__table__.update()
            .where(FaceDetection.id == fd_id)
            .values(cluster_id=original_cid)
        )
        touched_cluster_ids.add(original_cid)

    # Delete the new person (hard delete — it never had any other
    # state worth preserving for history since it was born on split).
    new_person = (
        await db.execute(
            select(TrustedPerson).where(TrustedPerson.id == new_person_id)
        )
    ).scalar_one_or_none()
    if new_person is not None:
        await db.delete(new_person)

    # Delete the new cluster now that it has no members.
    new_cluster = (
        await db.execute(
            select(FaceCluster).where(FaceCluster.id == new_cluster_id)
        )
    ).scalar_one_or_none()
    if new_cluster is not None:
        await db.delete(new_cluster)

    await db.flush()

    # Recompute member_count + centroid on every original cluster.
    for cid in touched_cluster_ids:
        count = (
            await db.execute(
                select(FaceDetection.id).where(
                    and_(
                        FaceDetection.cluster_id == cid,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        ).scalars().all()
        cluster = (
            await db.execute(select(FaceCluster).where(FaceCluster.id == cid))
        ).scalar_one_or_none()
        if cluster is None:
            continue
        cluster.member_count = len(count)
        centroid = await _compute_centroid_from_faces(cid, db)
        if centroid is not None:
            cluster.centroid_encrypted = centroid
    await db.flush()


async def _apply_undo_detach_face(
    payload: dict[str, Any], workspace_id: UUID, db: AsyncSession
) -> None:
    """Reverse a detach_face operation (S13-003).

    Restore the face's original cluster_id, recompute centroids on
    both clusters, soft-delete the now-empty new cluster, and rebuild
    photo edges for the affected person.
    """
    face_id = UUID(payload["face_detection_id"])
    new_cluster_id = UUID(payload["new_cluster_id"])
    original_cluster_id = UUID(payload["original_cluster_id"])
    person_id = UUID(payload["person_id"])

    face = (
        await db.execute(
            select(FaceDetection).where(FaceDetection.id == face_id)
        )
    ).scalar_one_or_none()
    if face is not None:
        face.cluster_id = original_cluster_id

    await db.flush()

    for cid in (original_cluster_id, new_cluster_id):
        cluster = (
            await db.execute(select(FaceCluster).where(FaceCluster.id == cid))
        ).scalar_one_or_none()
        if cluster is None:
            continue
        members = (
            await db.execute(
                select(FaceDetection.id).where(
                    and_(
                        FaceDetection.cluster_id == cid,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        ).scalars().all()
        cluster.member_count = len(members)
        if len(members) == 0 and cid == new_cluster_id:
            cluster.deleted_at = datetime.now(timezone.utc)
            continue
        recomputed = await _compute_centroid_from_faces(cid, db)
        if recomputed is not None:
            cluster.centroid_encrypted = recomputed
    await db.flush()

    from api.services.face import graph_edge_builder

    await graph_edge_builder.build_person_photo_edges(
        workspace_id=workspace_id, db=db, person_ids=[person_id]
    )


async def _apply_undo_rename(
    payload: dict[str, Any], db: AsyncSession
) -> None:
    person_id = UUID(payload["person_id"])
    old_name = payload["old_display_name"]
    p = (
        await db.execute(
            select(TrustedPerson).where(TrustedPerson.id == person_id)
        )
    ).scalar_one_or_none()
    if p is not None:
        p.display_name = old_name
    await db.flush()


async def _apply_undo_delete(
    payload: dict[str, Any], db: AsyncSession
) -> None:
    person_id = UUID(payload["person_id"])
    p = (
        await db.execute(
            select(TrustedPerson).where(TrustedPerson.id == person_id)
        )
    ).scalar_one_or_none()
    if p is not None:
        p.deleted_at = None
    await db.flush()


async def _apply_undo_confirm(
    payload: dict[str, Any], db: AsyncSession
) -> None:
    cluster_id = UUID(payload["cluster_id"])
    cluster = (
        await db.execute(select(FaceCluster).where(FaceCluster.id == cluster_id))
    ).scalar_one_or_none()
    if cluster is not None:
        cluster.cluster_state = "unconfirmed"
        cluster.trusted_person_id = None
    await db.flush()


async def _apply_undo_reject(
    payload: dict[str, Any], db: AsyncSession
) -> None:
    cluster_id = UUID(payload["cluster_id"])
    cluster = (
        await db.execute(select(FaceCluster).where(FaceCluster.id == cluster_id))
    ).scalar_one_or_none()
    if cluster is not None:
        cluster.cluster_state = payload.get("prior_state") or "unconfirmed"
    await db.flush()


_HANDLERS = {
    "merge": _apply_undo_merge,
    "split": _apply_undo_split,
}


# ── Public entry points ───────────────────────────────────────────────────


async def _apply(op: PersonOperation, workspace_id: UUID, db: AsyncSession) -> None:
    if op.undone_at is not None:
        raise ConflictError(
            error_code="OPERATION_ALREADY_UNDONE",
            message="Operation has already been undone.",
        )
    payload = op.inverse_payload or {}
    otype = op.operation_type
    if otype == "merge":
        await _apply_undo_merge(payload, workspace_id, db)
    elif otype == "split":
        await _apply_undo_split(payload, workspace_id, db)
    elif otype == "detach_face":
        await _apply_undo_detach_face(payload, workspace_id, db)
    elif otype == "rename":
        await _apply_undo_rename(payload, db)
    elif otype == "delete":
        await _apply_undo_delete(payload, db)
    elif otype == "confirm":
        await _apply_undo_confirm(payload, db)
    elif otype == "reject":
        await _apply_undo_reject(payload, db)
    else:  # pragma: no cover — CHECK constraint keeps us out of this branch
        raise ConflictError(
            error_code="OPERATION_NOT_FOUND",
            message=f"Unknown operation type: {otype}",
        )


async def undo_last_operation(
    *,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> OperationUndoResult:
    row = (
        await db.execute(
            select(PersonOperation)
            .where(
                and_(
                    PersonOperation.workspace_id == workspace_id,
                    PersonOperation.undone_at.is_(None),
                )
            )
            .order_by(PersonOperation.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(
            error_code="OPERATION_NOT_FOUND",
            message="No operations are available to undo.",
        )
    return await _finalize_undo(row, workspace_id, user_id, db)


async def undo_specific_operation(
    *,
    operation_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> OperationUndoResult:
    row = await _load_operation(operation_id, workspace_id, db)
    return await _finalize_undo(row, workspace_id, user_id, db)


async def _finalize_undo(
    row: PersonOperation,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> OperationUndoResult:
    await _apply(row, workspace_id, db)
    row.undone_at = datetime.now(timezone.utc)
    row.undone_by_user_id = user_id
    await db.flush()

    await audit.log_event(
        db=db,
        action="operation_undone",
        object_type="person_operations",
        object_id=row.id,
        user_id=user_id,
        workspace_id=workspace_id,
        metadata={
            "operation_id": str(row.id),
            "operation_type": row.operation_type,
        },
    )
    logger.info(
        "operation_undone",
        workspace_id=str(workspace_id),
        operation_id=str(row.id),
        operation_type=row.operation_type,
    )
    return OperationUndoResult(operation_id=row.id, operation_type=row.operation_type)
