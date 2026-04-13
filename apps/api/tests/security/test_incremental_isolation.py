"""Workspace isolation for incremental cluster assignment (S12-002).

Two consented workspaces. Ingesting a face in workspace A must not
affect any of workspace B's face_clusters (ids, member_counts, or
cluster_id assignments on B's face_detections). Partner test to
tests/security/test_clustering_isolation.py (S12-001 full re-cluster).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
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
from api.services.face import consent_service, crypto
from api.services.face.face_ingestion import process_photo_for_faces
from api.services.face.face_model import FaceResult

pytestmark = pytest.mark.asyncio(loop_scope="session")


class StatefulFakeQdrant:
    def __init__(self) -> None:
        self.points: dict[str, tuple[list[float], dict]] = {}

    async def upsert(self, *, collection_name, points):
        for p in points:
            self.points[str(p.id)] = (list(p.vector), dict(p.payload or {}))

    async def delete(self, **_):
        return None

    async def search(
        self,
        *,
        collection_name,
        query_vector,
        query_filter=None,
        limit=5,
        with_payload=True,
    ):
        q = np.asarray(list(query_vector), dtype=np.float32)
        qn = float(np.linalg.norm(q)) or 1.0
        q = q / qn

        must_ws: str | None = None
        must_not_fd: set[str] = set()
        if query_filter is not None:
            for cond in getattr(query_filter, "must", None) or []:
                if cond.key == "workspace_id":
                    must_ws = str(cond.match.value)
            for cond in getattr(query_filter, "must_not", None) or []:
                if cond.key == "face_detection_id":
                    must_not_fd.add(str(cond.match.value))

        scored = []
        for pid, (vec, payload) in self.points.items():
            if must_ws is not None and payload.get("workspace_id") != must_ws:
                continue
            if payload.get("face_detection_id") in must_not_fd:
                continue
            v = np.asarray(vec, dtype=np.float32)
            vn = float(np.linalg.norm(v)) or 1.0
            v = v / vn
            scored.append((float(np.dot(q, v)), pid, payload))
        scored.sort(key=lambda x: -x[0])
        return [
            SimpleNamespace(id=pid, score=sim, payload=payload)
            for sim, pid, payload in scored[:limit]
        ]


def _one_hot(dim: int) -> list[float]:
    v = [0.0] * 512
    v[dim] = 1.0
    return v


def _fake_model(dim: int) -> MagicMock:
    m = MagicMock()
    m.loaded = True
    m.load_error = None
    m.detector_version = "iso-det"
    m.recognizer_version = "iso-rec"
    m.load = MagicMock()
    m.detect_and_embed = MagicMock(
        return_value=[
            FaceResult(
                bbox={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                detection_score=0.95,
                embedding=_one_hot(dim),
            )
        ]
    )
    return m


async def _make_ws(db, owner_id: UUID, name: str) -> Workspace:
    ws = Workspace(name=name, type="personal", owner_id=owner_id)
    db.add(ws)
    await db.flush()
    db.add(
        WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role="admin")
    )
    await db.flush()
    return ws


async def _seed_photo(db, workspace_id: UUID, user_id: UUID, label: str):
    src = Source(
        workspace_id=workspace_id,
        name=f"iso-{label}-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()
    disk = f"/tmp/ekamcore-iso-{label}-{uuid4().hex}.jpg"
    Path(disk).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    f = File(
        workspace_id=workspace_id,
        source_id=src.id,
        filename=Path(disk).name,
        path=disk,
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=36,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()
    pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=0)
    db.add(pa)
    await db.flush()
    return pa.id


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
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)

    class _Pipe:
        def incr(self, *_):
            return self

        def expire(self, *_):
            return self

        async def execute(self):
            return [1, True]

    r.pipeline = lambda: _Pipe()
    with patch(
        "api.services.face.incremental_cluster.get_redis", return_value=r
    ):
        yield r


class TestIncrementalIsolation:
    async def test_workspace_a_ingest_leaves_b_untouched(
        self, test_session_factory, seed_user, face_env, stub_redis
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
            await db.commit()

        qdrant = StatefulFakeQdrant()

        # Seed workspace B with two photos of identity-B so it has
        # an existing cluster before A does anything.
        model_b = _fake_model(dim=300)
        for i in range(2):
            async with test_session_factory() as db:
                pa_id = await _seed_photo(db, ws_b_id, user_id, f"b{i}")
                await db.commit()
            async with test_session_factory() as db:
                await process_photo_for_faces(
                    pa_id, db, qdrant=qdrant, face_model=model_b
                )
                await db.commit()

        async with test_session_factory() as db:
            b_clusters_before = (
                (
                    await db.execute(
                        select(FaceCluster).where(
                            and_(
                                FaceCluster.workspace_id == ws_b_id,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            b_cluster_ids_before = {c.id for c in b_clusters_before}
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

        assert len(b_clusters_before) == 1
        assert b_clusters_before[0].member_count == 2

        # Now ingest in workspace A with a different identity.
        model_a = _fake_model(dim=42)
        async with test_session_factory() as db:
            pa_id = await _seed_photo(db, ws_a_id, user_id, "a0")
            await db.commit()
        async with test_session_factory() as db:
            await process_photo_for_faces(
                pa_id, db, qdrant=qdrant, face_model=model_a
            )
            await db.commit()

        async with test_session_factory() as db:
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
            b_clusters_after = (
                (
                    await db.execute(
                        select(FaceCluster).where(
                            and_(
                                FaceCluster.workspace_id == ws_b_id,
                                FaceCluster.deleted_at.is_(None),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            b_cluster_ids_after = {c.id for c in b_clusters_after}
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

        # A now has its own (disjoint) cluster
        assert len(a_clusters) == 1
        assert a_clusters[0].id not in b_cluster_ids_after
        # B is byte-for-byte identical
        assert b_cluster_ids_before == b_cluster_ids_after
        assert b_det_map_before == b_det_map_after
        assert b_clusters_after[0].member_count == 2
