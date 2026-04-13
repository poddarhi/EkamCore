"""Merge two or more trusted persons into one (S12-006).

``merge_persons`` is the forward path. ``undo_service`` applies the
captured inverse_payload to restore the pre-merge state exactly.

Design rules:

  1. **Keeper identity.** The caller names a keeper_id that MUST be
     in person_ids. The keeper keeps its id; every other person in
     the list is soft-deleted and recorded on
     ``keeper.merged_from_ids`` for historical attribution.

  2. **Cluster ownership moves.** Every ``face_clusters`` row
     previously linked to a non-keeper is rewritten to point at the
     keeper. The forward payload captures the move list so undo can
     move them back.

  3. **Graph edges rewrite.** ``graph_edges`` rows whose to_id is a
     non-keeper are rewritten to point at the keeper. Exact-duplicate
     edges (keeper already linked to the same contact) are dropped
     to preserve the UNIQUE (workspace_id, from_*, to_*, edge_type)
     constraint — the inverse payload remembers the dropped rows so
     undo can re-materialize them.

  4. **Workspace isolation.** Every query scopes on workspace_id.
     Attempting to merge a foreign person raises NotFoundError.

  5. **Atomicity.** All writes happen in the caller's transaction.
     On any error the merge rolls back; no partial state ever commits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.graph_edge import GraphEdge
from api.db.models.trusted_person import TrustedPerson
from api.errors import NotFoundError, ValidationError
from api.services import audit
from api.services.face import graph_edge_builder, operation_recorder

logger = structlog.get_logger()


async def _load_persons(
    person_ids: list[UUID], workspace_id: UUID, db: AsyncSession
) -> list[TrustedPerson]:
    rows = (
        (
            await db.execute(
                select(TrustedPerson).where(
                    and_(
                        TrustedPerson.id.in_(person_ids),
                        TrustedPerson.workspace_id == workspace_id,
                        TrustedPerson.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != len(set(person_ids)):
        raise NotFoundError(
            error_code="PERSON_NOT_FOUND",
            message="One or more persons were not found in this workspace.",
        )
    return list(rows)


async def merge_persons(
    *,
    person_ids: list[UUID],
    keeper_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> TrustedPerson:
    """Merge ``person_ids`` (≥2) into ``keeper_id``.

    Returns the updated keeper. Records a person_operations row
    with the inverse payload so the merge is reversible via
    ``undo_service``.
    """
    if len(person_ids) < 2:
        raise ValidationError(
            error_code="VALIDATION_ERROR",
            message="Merge requires at least two persons.",
        )
    if keeper_id not in person_ids:
        raise ValidationError(
            error_code="INVALID_MERGE_KEEPER",
            message="keeper_id must be one of the merged person_ids.",
        )

    persons = await _load_persons(list(set(person_ids)), workspace_id, db)
    persons_by_id = {p.id: p for p in persons}
    keeper = persons_by_id[keeper_id]
    non_keepers = [p for p in persons if p.id != keeper_id]

    now = datetime.now(timezone.utc)

    # Capture inverse state: every non-keeper's identity + its cluster ids.
    restored_persons: list[dict[str, Any]] = []
    cluster_moves: list[dict[str, Any]] = []

    for p in non_keepers:
        clusters = (
            (
                await db.execute(
                    select(FaceCluster).where(
                        and_(
                            FaceCluster.trusted_person_id == p.id,
                            FaceCluster.workspace_id == workspace_id,
                            FaceCluster.deleted_at.is_(None),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        cluster_ids = [c.id for c in clusters]
        restored_persons.append(
            {
                "person_id": str(p.id),
                "display_name": p.display_name,
                "canonical_contact_id": (
                    str(p.canonical_contact_id)
                    if p.canonical_contact_id is not None
                    else None
                ),
                "trust_source": p.trust_source,
                "confirmed_at": (
                    p.confirmed_at.isoformat() if p.confirmed_at else None
                ),
                "confirmed_by": (
                    str(p.confirmed_by) if p.confirmed_by is not None else None
                ),
                "merged_from_ids": p.merged_from_ids or [],
                "cluster_ids": [str(cid) for cid in cluster_ids],
            }
        )
        for cid in cluster_ids:
            cluster_moves.append(
                {
                    "cluster_id": str(cid),
                    "from_person_id": str(p.id),
                    "to_person_id": str(keeper_id),
                }
            )
            await db.execute(
                FaceCluster.__table__.update()
                .where(FaceCluster.id == cid)
                .values(trusted_person_id=keeper_id)
            )

        # Soft-delete the non-keeper.
        p.deleted_at = now

    # Capture keeper's pre-merge merged_from_ids for perfect undo.
    keeper_merged_from_before = list(keeper.merged_from_ids or [])
    new_merged_from = list(keeper_merged_from_before) + [
        str(p.id) for p in non_keepers
    ]
    keeper.merged_from_ids = new_merged_from

    # Graph-edge rewrite: anything pointing at a non-keeper becomes
    # an edge to the keeper. Drop exact duplicates against existing
    # keeper edges.
    edge_rewrites: list[dict[str, Any]] = []
    edge_drops: list[dict[str, Any]] = []
    for p in non_keepers:
        edges = (
            (
                await db.execute(
                    select(GraphEdge).where(
                        and_(
                            GraphEdge.workspace_id == workspace_id,
                            GraphEdge.to_type == "trusted_person",
                            GraphEdge.to_id == p.id,
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        for e in edges:
            # Is the keeper already linked with the same (from_type,
            # from_id, edge_type)?
            existing = (
                await db.execute(
                    select(GraphEdge.id).where(
                        and_(
                            GraphEdge.workspace_id == workspace_id,
                            GraphEdge.from_type == e.from_type,
                            GraphEdge.from_id == e.from_id,
                            GraphEdge.to_type == "trusted_person",
                            GraphEdge.to_id == keeper_id,
                            GraphEdge.edge_type == e.edge_type,
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                edge_drops.append(
                    {
                        "edge_id": str(e.id),
                        "from_type": e.from_type,
                        "from_id": str(e.from_id),
                        "to_type": e.to_type,
                        "to_id": str(e.to_id),
                        "edge_type": e.edge_type,
                        "strength": float(e.strength),
                        "evidence_json": e.evidence_json,
                    }
                )
                await db.delete(e)
            else:
                edge_rewrites.append(
                    {
                        "edge_id": str(e.id),
                        "original_to_id": str(e.to_id),
                    }
                )
                e.to_id = keeper_id

    await db.flush()

    forward_payload = {
        "keeper_id": str(keeper_id),
        "merged_ids": [str(p.id) for p in non_keepers],
        "cluster_moves": cluster_moves,
    }
    inverse_payload = {
        "keeper_id": str(keeper_id),
        "keeper_merged_from_ids_before": keeper_merged_from_before,
        "restored_persons": restored_persons,
        "edge_rewrites": edge_rewrites,
        "edge_drops": edge_drops,
    }

    await operation_recorder.record(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
        operation_type="merge",
        forward_payload=forward_payload,
        inverse_payload=inverse_payload,
    )

    await audit.log_event(
        db=db,
        action="persons_merged",
        object_type="trusted_persons",
        object_id=keeper_id,
        user_id=user_id,
        workspace_id=workspace_id,
        metadata={
            "keeper_id": str(keeper_id),
            "merged_count": len(non_keepers),
            "cluster_move_count": len(cluster_moves),
        },
    )
    logger.info(
        "persons_merged",
        workspace_id=str(workspace_id),
        keeper_id=str(keeper_id),
        merged_count=len(non_keepers),
        cluster_move_count=len(cluster_moves),
    )
    # S12-007: rebuild photo edges for the keeper — non-keepers are
    # soft-deleted so their edges are removed by the rebuild sweep.
    await graph_edge_builder.build_person_photo_edges(
        workspace_id=workspace_id,
        db=db,
        person_ids=[keeper_id, *(p.id for p in non_keepers)],
    )
    return keeper
