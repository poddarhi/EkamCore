"""Unit tests for incremental_cluster.assign_face_to_cluster (S12-002).

Five scenarios drive the decision tree directly by constructing
face_detection rows with fixed encrypted embeddings and stubbing a
Qdrant search to return specific neighbor scores. Each test asserts
one branch of the decision tree:

  - first face ever in workspace → mints a new cluster, member_count=1
  - highly similar to one existing cluster → joins, member_count=2
  - dissimilar from everyone → mints another new cluster
  - moderate similarity (0.55 <= sim < 0.70) → weak match, unclustered
  - drift guard on CONFIRMED cluster rejects an assignment

The Qdrant stand-in is a hand-rolled class with a synchronous
``.search`` declared async — deterministic, no external dependency.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import numpy as np
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import and_, select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
from api.services.face import crypto
from api.services.face.incremental_cluster import (
    STRONG_NEIGHBOR_SIM,
    WEAK_NEIGHBOR_SIM,
    assign_face_to_cluster,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ── Fake Qdrant with canned responses ───────────────────────────────────────


class _StatefulQdrant:
    """Minimal Qdrant stand-in. Tests call ``.prime()`` to set the
    scripted response for the next ``.search()`` call. Upsert and
    delete are no-ops."""

    def __init__(self) -> None:
        self._next_hits: list = []

    def prime(self, hits: list) -> None:
        self._next_hits = hits

    async def search(self, **_: object) -> list:
        return self._next_hits

    async def upsert(self, **_: object) -> None:
        return None

    async def delete(self, **_: object) -> None:
        return None


def _hit(score: float, face_detection_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid4()),
        score=score,
        payload={
            "face_detection_id": str(face_detection_id),
            "workspace_id": "",  # service doesn't use this
            "photo_asset_id": str(uuid4()),
            "face_detection_id": str(face_detection_id),
        },
    )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _one_hot(dim: int, n: int = 512) -> list[float]:
    v = [0.0] * n
    v[dim] = 1.0
    return v


async def _seed_face(
    db,
    workspace_id: UUID,
    user_id: UUID,
    *,
    embedding: list[float],
    cluster_id: UUID | None = None,
) -> UUID:
    """Insert one face_detection with the given encrypted embedding.
    Returns the new face_detection id."""
    src = Source(
        workspace_id=workspace_id,
        name=f"inc-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()
    f = File(
        workspace_id=workspace_id,
        source_id=src.id,
        filename=f"inc-{uuid4().hex[:6]}.jpg",
        path=f"/tmp/inc-{uuid4().hex}.jpg",
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=10,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()
    pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=1)
    db.add(pa)
    await db.flush()
    det = FaceDetection(
        workspace_id=workspace_id,
        photo_asset_id=pa.id,
        bbox_json={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        embedding_encrypted=crypto.encrypt_embedding(embedding),
        embedding_dim=512,
        detector_version="inc-det",
        recognizer_version="inc-rec",
        detection_score=0.9,
        qdrant_point_id=uuid4(),
        cluster_id=cluster_id,
    )
    db.add(det)
    await db.flush()
    return det.id


async def _seed_cluster(
    db,
    workspace_id: UUID,
    *,
    centroid: list[float],
    state: str = "unconfirmed",
    member_count: int = 1,
) -> UUID:
    row = FaceCluster(
        workspace_id=workspace_id,
        centroid_encrypted=crypto.encrypt_embedding(centroid),
        member_count=member_count,
        cluster_state=state,
    )
    db.add(row)
    await db.flush()
    return row.id


@pytest.fixture
def face_env():
    key = Fernet.generate_key().decode()
    with (
        patch.object(flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}),
        patch.object(flags.settings, "FACE_EMBED_KEY", key),
    ):
        crypto._reset_cache()
        try:
            yield key
        finally:
            crypto._reset_cache()


@pytest.fixture
def stub_redis():
    """Mock the recluster-hint Redis pipeline so tests don't touch a
    real instance. The pipeline object needs to support .incr/.expire/
    .execute, so we return a SimpleNamespace wired to AsyncMocks."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)

    class _Pipe:
        def incr(self, *_: object) -> "_Pipe":
            return self

        def expire(self, *_: object) -> "_Pipe":
            return self

        async def execute(self):
            return [1, True]

    r.pipeline = lambda: _Pipe()
    with patch(
        "api.services.face.incremental_cluster.get_redis", return_value=r
    ):
        yield r


# ── Tests ──────────────────────────────────────────────────────────────────


class TestIncrementalCluster:
    async def test_first_face_creates_new_cluster(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        """No existing neighbors → mints a new unconfirmed cluster
        with member_count=1 and an encrypted centroid."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            det_id = await _seed_face(
                db, ws, user_id, embedding=_one_hot(5)
            )
            await db.commit()

        qdrant = _StatefulQdrant()
        qdrant.prime([])  # no neighbors

        async with test_session_factory() as db:
            cluster_id = await assign_face_to_cluster(det_id, db, qdrant)
            await db.commit()

        assert cluster_id is not None

        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
            det = (
                await db.execute(
                    select(FaceDetection).where(FaceDetection.id == det_id)
                )
            ).scalar_one()
        assert cluster.member_count == 1
        assert cluster.cluster_state == "unconfirmed"
        assert cluster.centroid_encrypted is not None
        assert det.cluster_id == cluster_id

    async def test_second_similar_face_joins_cluster(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        """Top neighbor 0.95 + cluster centroid 0.95 → match, member_count=2."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            centroid = _one_hot(3)
            existing_cluster_id = await _seed_cluster(
                db, ws, centroid=centroid, member_count=1
            )
            neighbor_det_id = await _seed_face(
                db, ws, user_id,
                embedding=centroid,
                cluster_id=existing_cluster_id,
            )
            new_det_id = await _seed_face(
                db, ws, user_id, embedding=_one_hot(3)
            )
            await db.commit()

        qdrant = _StatefulQdrant()
        qdrant.prime([_hit(0.95, neighbor_det_id)])

        async with test_session_factory() as db:
            chosen = await assign_face_to_cluster(new_det_id, db, qdrant)
            await db.commit()

        assert chosen == existing_cluster_id

        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.id == existing_cluster_id
                    )
                )
            ).scalar_one()
            det = (
                await db.execute(
                    select(FaceDetection).where(FaceDetection.id == new_det_id)
                )
            ).scalar_one()
        assert cluster.member_count == 2
        assert det.cluster_id == existing_cluster_id

    async def test_dissimilar_face_creates_new_cluster(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        """Top neighbor < 0.55 → new cluster, not weak-match."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            centroid = _one_hot(10)
            existing_cluster_id = await _seed_cluster(
                db, ws, centroid=centroid
            )
            neighbor_det_id = await _seed_face(
                db, ws, user_id,
                embedding=centroid,
                cluster_id=existing_cluster_id,
            )
            new_det_id = await _seed_face(
                db, ws, user_id, embedding=_one_hot(20)
            )
            await db.commit()

        qdrant = _StatefulQdrant()
        qdrant.prime([_hit(0.10, neighbor_det_id)])  # well below 0.55

        async with test_session_factory() as db:
            chosen = await assign_face_to_cluster(new_det_id, db, qdrant)
            await db.commit()

        assert chosen is not None
        assert chosen != existing_cluster_id

        async with test_session_factory() as db:
            # Two clusters now — the original + the brand new one
            clusters = (
                (
                    await db.execute(
                        select(FaceCluster).where(
                            and_(
                                FaceCluster.workspace_id == ws,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(clusters) == 2

    async def test_moderate_similarity_is_weak_match(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        """Top neighbor in [0.55, 0.70) → weak, leave cluster_id NULL,
        no new cluster is minted."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            centroid = _one_hot(7)
            existing_cluster_id = await _seed_cluster(
                db, ws, centroid=centroid
            )
            neighbor_det_id = await _seed_face(
                db, ws, user_id,
                embedding=centroid,
                cluster_id=existing_cluster_id,
            )
            new_det_id = await _seed_face(
                db, ws, user_id, embedding=_one_hot(7)
            )
            await db.commit()

        qdrant = _StatefulQdrant()
        # Neighbor score 0.60 is above WEAK (0.55) but below STRONG
        # (0.70) → weak match decision.
        qdrant.prime([_hit(0.60, neighbor_det_id)])

        async with test_session_factory() as db:
            chosen = await assign_face_to_cluster(new_det_id, db, qdrant)
            await db.commit()

        assert chosen is None

        async with test_session_factory() as db:
            clusters = (
                (
                    await db.execute(
                        select(FaceCluster).where(
                            and_(
                                FaceCluster.workspace_id == ws,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            det = (
                await db.execute(
                    select(FaceDetection).where(FaceDetection.id == new_det_id)
                )
            ).scalar_one()
        assert len(clusters) == 1  # no new cluster was minted
        assert det.cluster_id is None

    async def test_confirmed_cluster_drift_guard_rejects(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        """A single-member CONFIRMED cluster's centroid would move
        by ~50% cosine distance if a perpendicular face joined it.
        The drift guard must reject the assignment and leave the new
        face unclustered."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            # Confirmed cluster seeded on one-hot dim 15, single member
            centroid = _one_hot(15)
            existing_cluster_id = await _seed_cluster(
                db, ws,
                centroid=centroid,
                state="confirmed",
                member_count=1,
            )
            neighbor_det_id = await _seed_face(
                db, ws, user_id,
                embedding=centroid,
                cluster_id=existing_cluster_id,
            )
            # New face is a copy of the centroid so the cluster_sim
            # threshold (0.60) and neighbor_sim threshold (0.70) both
            # pass, which is the only way to *reach* the drift check.
            # But we fake the Qdrant neighbor score as 1.0 on the
            # same neighbor (cluster_sim will compute from the
            # centroid directly).
            new_det_id = await _seed_face(
                db, ws, user_id, embedding=_one_hot(15)
            )
            await db.commit()

        qdrant = _StatefulQdrant()
        qdrant.prime([_hit(1.0, neighbor_det_id)])

        # Patch the drift threshold way down so our identical-vector
        # case (drift = 0.0) would normally pass — but we set the
        # threshold to -1 so *any* drift is "too much" and the guard
        # must refuse.
        with patch(
            "api.services.face.incremental_cluster.MAX_CENTROID_DRIFT_COSINE",
            -1.0,
        ):
            async with test_session_factory() as db:
                chosen = await assign_face_to_cluster(new_det_id, db, qdrant)
                await db.commit()

        assert chosen is None

        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.id == existing_cluster_id
                    )
                )
            ).scalar_one()
            det = (
                await db.execute(
                    select(FaceDetection).where(FaceDetection.id == new_det_id)
                )
            ).scalar_one()
        # Cluster unchanged (member_count still 1)
        assert cluster.member_count == 1
        # New face left unclustered
        assert det.cluster_id is None
