"""Split one trusted person into two (S12-006).

``split_person`` extracts a list of face_detection ids from an
existing person, creates a new face_cluster for them, and mints a
new trusted_person bound to that new cluster. The original person
retains every face_detection NOT in the split-out list.

Design rules:

  1. **Input validation.** Every face_detection_id must currently
     resolve to a cluster whose ``trusted_person_id`` is the person
     being split. A foreign or un-owned id raises
     ``SPLIT_FACES_NOT_FOUND`` — no partial split is ever produced.

  2. **Centroid recompute.** Both the new cluster and the original
     cluster have their centroids recomputed from their post-split
     members. Empty original clusters are allowed but rare — they
     occur when every member of a single-cluster person is split out.

  3. **Deterministic undo.** The inverse payload records, for every
     moved face_detection, the cluster it came from. Undo restores
     those cluster ids, deletes the new person + new cluster, and
     recomputes centroids using the pre-split member sets.

  4. **Workspace isolation + atomicity.** Same as merge_service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import numpy as np
import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.trusted_person import TrustedPerson
from api.errors import NotFoundError, ValidationError
from api.services import audit
from api.services.face import crypto, operation_recorder

logger = structlog.get_logger()


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(vec))
    if n <= 0:
        return vec
    return vec / n


async def _compute_centroid_from_faces(
    cluster_id: UUID, db: AsyncSession
) -> bytes | None:
    """Load every non-deleted face_detection in ``cluster_id``, decrypt
    its embedding, average, L2-normalize and re-encrypt. Returns None
    when the cluster has no members — in that case the caller should
    leave the previous centroid in place."""
    rows = (
        (
            await db.execute(
                select(FaceDetection.embedding_encrypted).where(
                    and_(
                        FaceDetection.cluster_id == cluster_id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    vectors: list[np.ndarray] = []
    for enc in rows:
        try:
            vec = crypto.decrypt_embedding(enc)
        except Exception:
            continue
        vectors.append(
            _l2_normalize(np.asarray(vec, dtype=np.float32))
        )
    if not vectors:
        return None
    mean = _l2_normalize(np.mean(np.stack(vectors, axis=0), axis=0))
    return crypto.encrypt_embedding(mean.tolist())


async def split_person(
    *,
    person_id: UUID,
    face_detection_ids: list[UUID],
    new_display_name: str,
    workspace_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> tuple[TrustedPerson, TrustedPerson]:
    """Split ``face_detection_ids`` out of ``person_id`` into a new
    trusted_person with a freshly-minted face_cluster.

    Returns ``(original_person, new_person)``.
    """
    if not face_detection_ids:
        raise ValidationError(
            error_code="VALIDATION_ERROR",
            message="At least one face_detection_id is required.",
        )
    if not new_display_name.strip():
        raise ValidationError(
            error_code="VALIDATION_ERROR",
            message="new_display_name is required.",
        )

    original = (
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
    if original is None:
        raise NotFoundError(
            error_code="PERSON_NOT_FOUND",
            message="Trusted person not found.",
        )

    # Load the face_detections and their current cluster assignments,
    # verifying each one lives in a cluster owned by this person.
    faces = (
        (
            await db.execute(
                select(FaceDetection).where(
                    and_(
                        FaceDetection.id.in_(face_detection_ids),
                        FaceDetection.workspace_id == workspace_id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if len(faces) != len(set(face_detection_ids)):
        raise ValidationError(
            error_code="SPLIT_FACES_NOT_FOUND",
            message="One or more face_detections were not found in this workspace.",
        )

    owning_cluster_ids = {
        f.cluster_id for f in faces if f.cluster_id is not None
    }
    if not owning_cluster_ids:
        raise ValidationError(
            error_code="SPLIT_FACES_NOT_FOUND",
            message="Face detections are not currently clustered.",
        )

    owning_clusters = (
        (
            await db.execute(
                select(FaceCluster).where(
                    and_(
                        FaceCluster.id.in_(owning_cluster_ids),
                        FaceCluster.workspace_id == workspace_id,
                        FaceCluster.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for c in owning_clusters:
        if c.trusted_person_id != person_id:
            raise ValidationError(
                error_code="SPLIT_FACES_NOT_FOUND",
                message=(
                    "One or more face_detections do not belong to the "
                    "given person."
                ),
            )

    # Inverse snapshot: for every moved face, remember its original cluster.
    face_detection_restores = [
        {
            "face_detection_id": str(f.id),
            "cluster_id": str(f.cluster_id),
        }
        for f in faces
    ]
    pre_split_member_counts = {
        str(c.id): int(c.member_count or 0) for c in owning_clusters
    }

    # Create the new cluster (empty, centroid filled in after reassignment).
    new_cluster = FaceCluster(
        workspace_id=workspace_id,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=len(faces),
        cluster_state="confirmed",
    )
    db.add(new_cluster)
    await db.flush()

    # Reassign face_detections to the new cluster.
    for f in faces:
        f.cluster_id = new_cluster.id
    await db.flush()

    # Recompute centroid for the new cluster now that it has its members.
    new_centroid = await _compute_centroid_from_faces(new_cluster.id, db)
    if new_centroid is not None:
        new_cluster.centroid_encrypted = new_centroid

    # Decrement and recompute each original cluster.
    for c in owning_clusters:
        remaining = (
            await db.execute(
                select(FaceDetection.id).where(
                    and_(
                        FaceDetection.cluster_id == c.id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
            )
        ).scalars().all()
        c.member_count = len(remaining)
        recomputed = await _compute_centroid_from_faces(c.id, db)
        if recomputed is not None:
            c.centroid_encrypted = recomputed

    # Create the new trusted_person and bind the new cluster to it.
    now = datetime.now(timezone.utc)
    new_person = TrustedPerson(
        workspace_id=workspace_id,
        display_name=new_display_name.strip(),
        trust_source="manual",
        confirmed_at=now,
        confirmed_by=user_id,
    )
    db.add(new_person)
    await db.flush()
    new_cluster.trusted_person_id = new_person.id
    await db.flush()

    forward_payload = {
        "original_person_id": str(person_id),
        "new_person_id": str(new_person.id),
        "new_cluster_id": str(new_cluster.id),
        "moved_count": len(faces),
    }
    inverse_payload = {
        "original_person_id": str(person_id),
        "new_person_id": str(new_person.id),
        "new_cluster_id": str(new_cluster.id),
        "face_detection_restores": face_detection_restores,
        "pre_split_member_counts": pre_split_member_counts,
    }

    await operation_recorder.record(
        db=db,
        workspace_id=workspace_id,
        user_id=user_id,
        operation_type="split",
        forward_payload=forward_payload,
        inverse_payload=inverse_payload,
    )

    await audit.log_event(
        db=db,
        action="person_split",
        object_type="trusted_persons",
        object_id=person_id,
        user_id=user_id,
        workspace_id=workspace_id,
        metadata={
            "original_person_id": str(person_id),
            "new_person_id": str(new_person.id),
            "new_cluster_id": str(new_cluster.id),
            "moved_count": len(faces),
        },
    )
    logger.info(
        "person_split",
        workspace_id=str(workspace_id),
        original_person_id=str(person_id),
        new_person_id=str(new_person.id),
        moved_count=len(faces),
    )
    return original, new_person
