"""Integration test for cluster_workspace end-to-end (S12-001).

Seeds ~100 face_detections across 10 synthetic identities, runs
cluster_workspace with an injected fake hdbscan, then asserts:
  - face_clusters rows created with matching member_counts
  - face_detections.cluster_id populated for every non-noise detection
  - centroid_encrypted is non-null for every cluster
  - audit_log row ``face_clusters_recomputed`` written with counts
  - re-running reuses the same cluster ids for unchanged membership
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import numpy as np
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import and_, select

from api.db.models.audit_log import AuditLog
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
from api.services.face import clustering_service, consent_service, crypto
from api.services.face.clustering_service import cluster_workspace

pytestmark = pytest.mark.asyncio(loop_scope="session")

_NOISE_DIM = 511


def _embedding_for_label(label: int) -> list[float]:
    vec = [0.0] * 512
    vec[_NOISE_DIM if label < 0 else label] = 1.0
    return vec


def _labels_by_argmax(X: np.ndarray) -> list[int]:
    labels = []
    for row in X:
        idx = int(np.argmax(row))
        labels.append(-1 if idx == _NOISE_DIM else idx)
    return labels


def _fake_hdbscan():
    class _FakeHDBSCAN:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.labels_ = np.array([], dtype=int)
            self.probabilities_ = np.array([], dtype=float)

        def fit(self, X):
            lbls = _labels_by_argmax(X)
            self.labels_ = np.asarray(lbls, dtype=int)
            self.probabilities_ = np.ones(len(lbls))
            return self

    m = MagicMock()
    m.HDBSCAN = _FakeHDBSCAN
    return m


async def _seed(db, workspace_id, user_id, labels: list[int]) -> list[UUID]:
    src = Source(
        workspace_id=workspace_id,
        name=f"int-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()
    det_ids: list[UUID] = []
    for i, label in enumerate(labels):
        f = File(
            workspace_id=workspace_id,
            source_id=src.id,
            filename=f"int-{i}.jpg",
            path=f"/tmp/int-{uuid4().hex}.jpg",
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
            embedding_encrypted=crypto.encrypt_embedding(
                _embedding_for_label(label)
            ),
            embedding_dim=512,
            detector_version="t-det",
            recognizer_version="t-rec",
            detection_score=0.9,
            qdrant_point_id=uuid4(),
        )
        db.add(det)
        await db.flush()
        det_ids.append(det.id)
    return det_ids


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


class TestClusteringFullRun:
    async def test_100_faces_10_identities_full_run(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        labels = [i % 10 for i in range(100)]  # 10 per identity
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            await _seed(db, ws, user_id, labels)
            await db.commit()

        async with test_session_factory() as db:
            report = await cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()

        assert report.face_count == 100
        assert report.cluster_count == 10
        assert report.noise_count == 0
        assert report.new_cluster_count == 10
        assert report.before_cluster_count == 0

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
            detections = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws
                        )
                    )
                )
                .scalars()
                .all()
            )
            audit_rows = (
                (
                    await db.execute(
                        select(AuditLog).where(
                            and_(
                                AuditLog.workspace_id == ws,
                                AuditLog.action == "face_clusters_recomputed",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert len(clusters) == 10
        assert all(c.centroid_encrypted for c in clusters)
        assert sum(c.member_count for c in clusters) == 100
        assert all(d.cluster_id is not None for d in detections)
        assert len(audit_rows) >= 1
        # Audit metadata captures counts
        meta = audit_rows[-1].metadata_json or {}
        assert meta.get("after_count") == 10
        assert meta.get("face_count") == 100
        assert meta.get("noise_count") == 0

    async def test_rerun_reuses_cluster_ids_by_majority_overlap(
        self, test_session_factory, seed_user, face_env
    ):
        """A second run over the same workspace should reuse the
        existing face_clusters rows rather than minting new ones."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        labels = [i % 5 for i in range(20)]
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            await _seed(db, ws, user_id, labels)
            await db.commit()

        async with test_session_factory() as db:
            first = await cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()

        async with test_session_factory() as db:
            cluster_ids_before = set(
                (
                    await db.execute(
                        select(FaceCluster.id).where(
                            and_(
                                FaceCluster.workspace_id == ws,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                ).scalars().all()
            )

        async with test_session_factory() as db:
            second = await cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()

        async with test_session_factory() as db:
            cluster_ids_after = set(
                (
                    await db.execute(
                        select(FaceCluster.id).where(
                            and_(
                                FaceCluster.workspace_id == ws,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                ).scalars().all()
            )

        assert first.cluster_count == 5
        assert second.cluster_count == 5
        # Identity stability: re-run reuses all 5 existing cluster ids
        assert cluster_ids_before == cluster_ids_after
        assert second.reused_cluster_count == 5
        assert second.new_cluster_count == 0
