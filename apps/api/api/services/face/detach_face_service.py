"""Detach a single face_detection from a trusted person (S13-003).

The Person detail page exposes a "this isn't them" correction — the
user clicks an X on a face thumbnail and the face is moved off the
person into a new 1-member ``unconfirmed`` cluster (no
``trusted_person_id``). The face itself is preserved so a future
review pass can reassign it; only its cluster membership changes.

Why a dedicated service rather than reusing ``split_service``?
  - ``split_person`` produces a brand-new *confirmed* trusted_person.
    The correction flow needs an *unconfirmed floating cluster* with
    no person bound to it.
  - The undo semantics are simpler: restore the original cluster_id
    on the single face and soft-delete the new cluster.

Design rules:

  1. **Workspace isolation.** Every SELECT is scoped on workspace_id.
  2. **Confused-deputy guard.** The face must currently belong to a
     cluster owned by ``person_id``; otherwise FACE_NOT_IN_PERSON.
  3. **Atomicity.** All mutations + operation_log + audit_log + edge
     rebuild flush in the caller's transaction.
  4. **Recompute centroids.** Both the donor cluster and the new
     1-member cluster get fresh centroids so future scoring stays
     accurate.
  5. **Undo trail.** ``person_operations`` row of type ``detach_face``
     records the original cluster_id so the inverse operation can
     restore it exactly.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.errors import NotFoundError, ValidationError
from api.services import audit
from api.services.face import crypto, graph_edge_builder, operation_recorder
from api.services.face.split_service import _compute_centroid_from_faces

logger = structlog.get_logger()


async def detach_face(
    *,
    person_id: UUID,
    face_detection_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> UUID:
    """Detach ``face_detection_id`` from ``person_id``.

    Returns the new (unconfirmed, 1-member) ``cluster_id`` so the
    router can include it in audit logs and the test suite can
    assert on it.
    """
    face = (
        await db.execute(
            select(FaceDetection).where(
                and_(
                    FaceDetection.id == face_detection_id,
                    FaceDetection.workspace_id == workspace_id,
                    FaceDetection.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if face is None:
        raise NotFoundError(
            error_code="FACE_NOT_FOUND",
            message="Face detection not found.",
        )
    if face.cluster_id is None:
        raise ValidationError(
            error_code="FACE_NOT_IN_PERSON",
            message="Face is not currently clustered.",
        )

    original_cluster = (
        await db.execute(
            select(FaceCluster).where(
                and_(
                    FaceCluster.id == face.cluster_id,
                    FaceCluster.workspace_id == workspace_id,
                    FaceCluster.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if original_cluster is None or original_cluster.trusted_person_id != person_id:
        raise ValidationError(
            error_code="FACE_NOT_IN_PERSON",
            message="Face does not belong to the given person.",
        )

    original_cluster_id = original_cluster.id
    original_member_count = int(original_cluster.member_count or 0)

    # Mint a new floating, unconfirmed cluster with a placeholder
    # centroid; the real one is computed after the face moves.
    new_cluster = FaceCluster(
        workspace_id=workspace_id,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=1,
        cluster_state="unconfirmed",
        trusted_person_id=None,
    )
    db.add(new_cluster)
    await db.flush()

    face.cluster_id = new_cluster.id
    await db.flush()

    new_centroid = await _compute_centroid_from_faces(new_cluster.id, db)
    if new_centroid is not None:
        new_cluster.centroid_encrypted = new_centroid

    # Recompute the donor cluster.
    remaining = (
        await db.execute(
            select(FaceDetection.id).where(
                and_(
                    FaceDetection.cluster_id == original_cluster_id,
                    FaceDetection.deleted_at.is_(None),
                )
            )
        )
    ).scalars().all()
    original_cluster.member_count = len(remaining)
    recomputed = await _compute_centroid_from_faces(original_cluster_id, db)
    if recomputed is not None:
        original_cluster.centroid_encrypted = recomputed

    forward_payload = {
        "person_id": str(person_id),
        "face_detection_id": str(face_detection_id),
        "new_cluster_id": str(new_cluster.id),
        "original_cluster_id": str(original_cluster_id),
    }
    inverse_payload = {
        "person_id": str(person_id),
        "face_detection_id": str(face_detection_id),
        "new_cluster_id": str(new_cluster.id),
        "original_cluster_id": str(original_cluster_id),
        "original_member_count": original_member_count,
    }

    await operation_recorder.record(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
        operation_type="detach_face",
        forward_payload=forward_payload,
        inverse_payload=inverse_payload,
    )

    await audit.log_event(
        db=db,
        action="person_detach_face",
        object_type="trusted_persons",
        object_id=person_id,
        user_id=user_id,
        workspace_id=workspace_id,
        metadata={
            "face_detection_id": str(face_detection_id),
            "new_cluster_id": str(new_cluster.id),
            "original_cluster_id": str(original_cluster_id),
        },
    )
    logger.info(
        "person_detach_face",
        workspace_id=str(workspace_id),
        person_id=str(person_id),
        new_cluster_id=str(new_cluster.id),
    )

    # The face may have been the only one connecting this person
    # to a particular photo — rebuild edges so the appears_in set
    # reflects the new membership.
    await graph_edge_builder.build_person_photo_edges(
        workspace_id=workspace_id,
        db=db,
        person_ids=[person_id],
    )
    return new_cluster.id
