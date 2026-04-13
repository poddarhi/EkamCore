"""Workspace isolation for ClusteringService (S12-001).

Two independently-consented workspaces each get face data. Running
cluster_workspace against workspace A must leave workspace B's
face_clusters and face_detections.cluster_id completely untouched.
Partner to tests/security/test_face_workspace_isolation.py (S11-006)
and tests/security/test_hard_delete_isolation.py (S11-003).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
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
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.face import clustering_service, consent_service, crypto
from api.services.face.clustering_service import cluster_workspace

pytestmark = pytest.mark.asyncio(loop_scope="session")

_NOISE_DIM = 511


def _emb(label: int) -> list[float]:
    v = [0.0] * 512
    v[_NOISE_DIM if label < 0 else label] = 1.0
    return v


def _fake_hdbscan():
    class _FakeHDBSCAN:
        def __init__(self, **kwargs):
            self.labels_ = np.array([], dtype=int)
            self.probabilities_ = np.array([], dtype=float)

        def fit(self, X):
            labels = [
                -1 if int(np.argmax(row)) == _NOISE_DIM else int(np.argmax(row))
                for row in X
            ]
            self.labels_ = np.asarray(labels, dtype=int)
            self.probabilities_ = np.ones(len(labels))
            return self

    m = MagicMock()
    m.HDBSCAN = _FakeHDBSCAN
    return m


async def _make_ws(db, owner_id: UUID, name: str) -> Workspace:
    ws = Workspace(name=name, type="personal", owner_id=owner_id)
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role="admin"))
    await db.flush()
    return ws


async def _seed(db, workspace_id: UUID, user_id: UUID, labels: list[int]) -> None:
    src = Source(
        workspace_id=workspace_id,
        name=f"iso-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()
    for i, label in enumerate(labels):
        f = File(
            workspace_id=workspace_id,
            source_id=src.id,
            filename=f"iso-{i}.jpg",
            path=f"/tmp/iso-{uuid4().hex}.jpg",
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
            embedding_encrypted=crypto.encrypt_embedding(_emb(label)),
            embedding_dim=512,
            detector_version="iso-det",
            recognizer_version="iso-rec",
            detection_score=0.9,
            qdrant_point_id=uuid4(),
        )
        db.add(det)
        await db.flush()


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


class TestClusteringIsolation:
    async def test_recluster_a_leaves_b_untouched(
        self, test_session_factory, seed_user, face_env
    ):
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            ws_a = await _make_ws(db, user_id, "A")
            ws_b = await _make_ws(db, user_id, "B")
            await db.commit()
            ws_a_id = ws_a.id
            ws_b_id = ws_b.id

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws_a_id, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            await consent_service.grant(
                workspace_id=ws_b_id, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            # 3 clusters in A, 2 clusters in B
            await _seed(db, ws_a_id, user_id, [0, 0, 0, 1, 1, 1, 2, 2, 2])
            await _seed(db, ws_b_id, user_id, [10, 10, 10, 11, 11, 11])
            await db.commit()

        # Pre-cluster B so it has existing face_clusters rows
        async with test_session_factory() as db:
            b_first = await cluster_workspace(
                ws_b_id, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()

        async with test_session_factory() as db:
            b_cluster_ids_before = {
                cid for cid in (
                    await db.execute(
                        select(FaceCluster.id).where(
                            and_(
                                FaceCluster.workspace_id == ws_b_id,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                ).scalars().all()
            }
            b_det_map_before = {
                d.id: d.cluster_id
                for d in (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws_b_id
                        )
                    )
                ).scalars().all()
            }

        # Now re-cluster workspace A.
        async with test_session_factory() as db:
            a_report = await cluster_workspace(
                ws_a_id, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()

        async with test_session_factory() as db:
            b_cluster_ids_after = {
                cid for cid in (
                    await db.execute(
                        select(FaceCluster.id).where(
                            and_(
                                FaceCluster.workspace_id == ws_b_id,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                ).scalars().all()
            }
            b_det_map_after = {
                d.id: d.cluster_id
                for d in (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws_b_id
                        )
                    )
                ).scalars().all()
            }
            a_clusters = (
                (
                    await db.execute(
                        select(FaceCluster).where(
                            and_(
                                FaceCluster.workspace_id == ws_a_id,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert a_report.cluster_count == 3
        assert len(a_clusters) == 3
        # B's clusters unchanged — same ids, same memberships
        assert b_cluster_ids_before == b_cluster_ids_after
        assert b_det_map_before == b_det_map_after
        # No A cluster id has bled into B's rows
        a_cluster_ids = {c.id for c in a_clusters}
        assert a_cluster_ids.isdisjoint(b_cluster_ids_after)
        for det_cid in b_det_map_after.values():
            assert det_cid not in a_cluster_ids
