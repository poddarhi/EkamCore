"""Unit tests for ClusteringService (S12-001).

The real `hdbscan` library is not installed in the dev environment
(per the S12-001 deferred-install pattern). We inject a fake hdbscan
module into `cluster_workspace` via the `hdbscan_module=` kwarg. The
fake's `HDBSCAN.fit()` produces exact labels computed deterministically
from the input vectors — each test constructs inputs whose clustering
outcome is known.

These tests cover the orchestration logic: consent gating, detection
loading, L2-normalize, label grouping, identity-stability match,
centroid recompute + encrypt, audit emission, bulk cluster_id updates.
Real HDBSCAN quality (precision/recall targets from ART-25 §3.2) is
exercised separately by the ML eval harness in
``scripts/eval/eval_face_detection.py`` + Sprint 12's clustering eval
follow-up, which requires the real library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
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
from api.services.face.clustering_service import (
    ClusteringParams,
    cluster_workspace,
    get_clustering_params,
    set_clustering_params,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ── Fake hdbscan module ────────────────────────────────────────────────────


def _fake_hdbscan_with_labels(labels_func):
    """Build a stand-in for the `hdbscan` module whose HDBSCAN.fit()
    produces labels by calling `labels_func(input_array)`. The returned
    module has exactly one attribute (``HDBSCAN``) that the service
    reaches for.
    """

    class _FakeHDBSCAN:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.labels_: np.ndarray = np.array([], dtype=int)
            self.probabilities_: np.ndarray = np.array([], dtype=float)

        def fit(self, X: np.ndarray) -> "_FakeHDBSCAN":
            lbls = labels_func(X)
            self.labels_ = np.asarray(lbls, dtype=int)
            self.probabilities_ = np.ones(len(lbls), dtype=float)
            return self

    module = MagicMock()
    module.HDBSCAN = _FakeHDBSCAN
    return module


# Dimension 511 is reserved as the "noise" marker — argmax landing
# there means "this is a noise point" (label -1). All other dims
# correspond 1:1 to cluster labels.
_NOISE_DIM = 511


def _labels_by_argmax(X: np.ndarray) -> list[int]:
    """Deterministic label function robust to L2-normalization.

    The service L2-normalizes the input before handing it to
    HDBSCAN.fit. One-hot vectors survive normalization unchanged,
    so ``argmax`` of each row deterministically recovers the label
    the test encoded. Dimension ``_NOISE_DIM`` is the noise sentinel.
    """
    labels: list[int] = []
    for row in X:
        idx = int(np.argmax(row))
        labels.append(-1 if idx == _NOISE_DIM else idx)
    return labels


# ── Helpers ─────────────────────────────────────────────────────────────────


def _embedding_for_label(label: int) -> list[float]:
    """Build a 512-dim one-hot vector whose dominant dimension is
    the label id (or ``_NOISE_DIM`` for noise). After L2-normalize
    the dominant dim is still exactly 1.0, so the fake labeler's
    ``argmax`` recovers ``label`` unchanged."""
    vec = [0.0] * 512
    if label < 0:
        vec[_NOISE_DIM] = 1.0
    else:
        vec[label] = 1.0
    return vec


async def _seed_workspace(
    db, workspace_id, *, registered_by, face_labels: list[int]
) -> list[UUID]:
    """Seed N face_detections for the given workspace with embeddings
    whose fake-HDBSCAN label is determined by ``face_labels``. Returns
    the list of FaceDetection ids in the order inserted."""
    src = Source(
        workspace_id=workspace_id,
        name=f"clust-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=registered_by,
        status="active",
    )
    db.add(src)
    await db.flush()

    det_ids: list[UUID] = []
    for i, label in enumerate(face_labels):
        f = File(
            workspace_id=workspace_id,
            source_id=src.id,
            filename=f"clust-{i}.jpg",
            path=f"/tmp/clust-{uuid4().hex}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10,
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=1)
        db.add(pa)
        await db.flush()

        vec = _embedding_for_label(label)
        det = FaceDetection(
            workspace_id=workspace_id,
            photo_asset_id=pa.id,
            bbox_json={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            embedding_encrypted=crypto.encrypt_embedding(vec),
            embedding_dim=512,
            detector_version="test-det",
            recognizer_version="test-rec",
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


async def _grant_consent(db, workspace_id, user_id) -> None:
    await consent_service.grant(
        workspace_id=workspace_id,
        user_id=user_id,
        ip="127.0.0.1",
        user_agent="pytest",
        db=db,
    )


# ── Tests ──────────────────────────────────────────────────────────────────


class TestClusteringService:
    async def test_five_synthetic_clusters(
        self, test_session_factory, seed_user, face_env
    ):
        """50 embeddings across 5 identities → 5 clusters, 0 noise."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        labels = [i for i in range(5) for _ in range(10)]
        async with test_session_factory() as db:
            await _grant_consent(db, ws, user_id)
            await _seed_workspace(
                db, ws, registered_by=user_id, face_labels=labels
            )
            await db.commit()

        fake = _fake_hdbscan_with_labels(_labels_by_argmax)
        async with test_session_factory() as db:
            report = await cluster_workspace(
                ws, db, hdbscan_module=fake
            )
            await db.commit()

        assert report.face_count == 50
        assert report.cluster_count == 5
        assert report.noise_count == 0
        assert report.before_cluster_count == 0
        assert report.new_cluster_count == 5

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
        assert len(clusters) == 5
        # Every cluster has a non-null encrypted centroid
        assert all(c.centroid_encrypted for c in clusters)
        assert all(c.member_count == 10 for c in clusters)
        # Every detection is assigned to one of the 5 new clusters
        assigned = {d.cluster_id for d in detections}
        assert None not in assigned
        assert len(assigned) == 5

    async def test_all_noise(
        self, test_session_factory, seed_user, face_env
    ):
        """10 vectors all labeled -1 → 0 clusters, 10 noise, no crash."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await _grant_consent(db, ws, user_id)
            # label -1 via our labeler requires first component negative
            await _seed_workspace(
                db, ws, registered_by=user_id, face_labels=[-1] * 10
            )
            await db.commit()

        fake = _fake_hdbscan_with_labels(_labels_by_argmax)
        async with test_session_factory() as db:
            report = await cluster_workspace(
                ws, db, hdbscan_module=fake
            )
            await db.commit()

        assert report.face_count == 10
        assert report.cluster_count == 0
        assert report.noise_count == 10
        async with test_session_factory() as db:
            clusters = (
                (
                    await db.execute(
                        select(FaceCluster).where(
                            FaceCluster.workspace_id == ws
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
        assert clusters == []
        assert all(d.cluster_id is None for d in detections)

    async def test_empty_workspace(
        self, test_session_factory, seed_user, face_env
    ):
        """No face_detections → 0 clusters, 0 noise, audit still written."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await _grant_consent(db, ws, user_id)
            await db.commit()

        fake = _fake_hdbscan_with_labels(_labels_by_argmax)
        async with test_session_factory() as db:
            report = await cluster_workspace(
                ws, db, hdbscan_module=fake
            )
            await db.commit()

        assert report.face_count == 0
        assert report.cluster_count == 0
        assert report.noise_count == 0

        async with test_session_factory() as db:
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
        assert len(audit_rows) >= 1

    async def test_consent_inactive_raises(
        self, test_session_factory, seed_user, face_env
    ):
        """cluster_workspace without active consent → raises FaceConsentRequiredError."""
        from api.errors import FaceConsentRequiredError

        ws = seed_user["workspace_id"]
        # Note: no consent granted.

        fake = _fake_hdbscan_with_labels(_labels_by_argmax)
        async with test_session_factory() as db:
            with pytest.raises(FaceConsentRequiredError):
                await cluster_workspace(ws, db, hdbscan_module=fake)


class TestClusteringParams:
    async def test_defaults_when_unset(
        self, test_session_factory, seed_user
    ):
        ws = seed_user["workspace_id"]
        async with test_session_factory() as db:
            params = await get_clustering_params(ws, db)
        assert params.min_cluster_size == 3
        assert params.cluster_selection_epsilon == pytest.approx(0.35)

    async def test_set_then_get_roundtrip(
        self, test_session_factory, seed_user
    ):
        ws = seed_user["workspace_id"]
        async with test_session_factory() as db:
            await set_clustering_params(
                ws,
                ClusteringParams(min_cluster_size=5, cluster_selection_epsilon=0.25),
                db,
            )
            await db.commit()

        async with test_session_factory() as db:
            params = await get_clustering_params(ws, db)
        assert params.min_cluster_size == 5
        assert params.cluster_selection_epsilon == pytest.approx(0.25)
