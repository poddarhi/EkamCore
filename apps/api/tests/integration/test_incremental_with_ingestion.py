"""Integration test for incremental clustering wired through
``process_photo_for_faces`` (S12-002).

Exercises the real S11-006 ingestion path with a stateful fake
Qdrant that actually performs a brute-force nearest-neighbor search,
so incremental assignment sees the previously-upserted embeddings
exactly like a real Qdrant instance would. Two scenarios:

  - 10 photos of the same identity → one cluster with member_count 10
  - 10 more photos of a second identity → second cluster with
    member_count 10, total 2 clusters
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
from api.services import flags
from api.services.face import consent_service, crypto
from api.services.face.face_ingestion import process_photo_for_faces
from api.services.face.face_model import FaceResult

pytestmark = pytest.mark.asyncio(loop_scope="session")

_NOISE_DIM = 511


# ── Stateful fake Qdrant ───────────────────────────────────────────────────


class StatefulFakeQdrant:
    """In-memory Qdrant stand-in that supports upsert + search with
    the exact filter shape the incremental service uses
    (workspace_id must + face_detection_id must_not)."""

    def __init__(self) -> None:
        # id -> (vector, payload)
        self.points: dict[str, tuple[list[float], dict]] = {}

    async def upsert(self, *, collection_name: str, points) -> None:
        for p in points:
            vec = list(p.vector)
            payload = dict(p.payload or {})
            self.points[str(p.id)] = (vec, payload)
        return None

    async def delete(self, **_: object) -> None:
        return None

    async def search(
        self,
        *,
        collection_name: str,
        query_vector,
        query_filter=None,
        limit: int = 5,
        with_payload: bool = True,
    ):
        q = np.asarray(list(query_vector), dtype=np.float32)
        qn = float(np.linalg.norm(q))
        if qn > 0:
            q = q / qn

        must_workspace_id: str | None = None
        must_not_face_det_ids: set[str] = set()
        if query_filter is not None:
            for cond in getattr(query_filter, "must", None) or []:
                if cond.key == "workspace_id":
                    must_workspace_id = str(cond.match.value)
            for cond in getattr(query_filter, "must_not", None) or []:
                if cond.key == "face_detection_id":
                    must_not_face_det_ids.add(str(cond.match.value))

        scored: list[tuple[float, str, dict]] = []
        for pid, (vec, payload) in self.points.items():
            if (
                must_workspace_id is not None
                and payload.get("workspace_id") != must_workspace_id
            ):
                continue
            if payload.get("face_detection_id") in must_not_face_det_ids:
                continue
            v = np.asarray(vec, dtype=np.float32)
            vn = float(np.linalg.norm(v))
            if vn > 0:
                v = v / vn
            sim = float(np.dot(q, v))
            scored.append((sim, pid, payload))

        scored.sort(key=lambda x: -x[0])
        results = []
        for sim, pid, payload in scored[:limit]:
            results.append(SimpleNamespace(id=pid, score=sim, payload=payload))
        return results


# ── Face pipeline fakes (same pattern as S11-006 tests) ────────────────────


def _one_hot(dim: int) -> list[float]:
    v = [0.0] * 512
    v[dim] = 1.0
    return v


def _fake_face_for(dim: int, score: float = 0.95) -> FaceResult:
    return FaceResult(
        bbox={"x": 10.0, "y": 20.0, "w": 100.0, "h": 120.0},
        detection_score=score,
        embedding=_one_hot(dim),
    )


def _fake_face_model(embedding_dim: int) -> MagicMock:
    m = MagicMock()
    m.loaded = True
    m.load_error = None
    m.detector_version = "inc-det"
    m.recognizer_version = "inc-rec"
    m.load = MagicMock()
    m.detect_and_embed = MagicMock(
        return_value=[_fake_face_for(embedding_dim)]
    )
    return m


async def _seed_photo(db, workspace_id, user_id, *, label: str):
    src = Source(
        workspace_id=workspace_id,
        name=f"ii-{label}-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()
    disk = f"/tmp/ekamcore-ii-{label}-{uuid4().hex}.jpg"
    Path(disk).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    f = File(
        workspace_id=workspace_id,
        source_id=src.id,
        filename=Path(disk).name,
        path=disk,
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=68,
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


class TestIncrementalWithIngestion:
    async def test_10_same_identity_converge_to_one_cluster(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            await db.commit()

        qdrant = StatefulFakeQdrant()
        model = _fake_face_model(embedding_dim=42)  # identity A

        # Ingest 10 photos, each producing a single face of identity A.
        for i in range(10):
            async with test_session_factory() as db:
                pa_id = await _seed_photo(db, ws, user_id, label=f"a{i}")
                await db.commit()
            async with test_session_factory() as db:
                await process_photo_for_faces(
                    pa_id, db, qdrant=qdrant, face_model=model
                )
                await db.commit()

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
        assert len(clusters) == 1
        assert clusters[0].member_count == 10
        assert all(d.cluster_id == clusters[0].id for d in detections)

    async def test_two_identities_produce_two_clusters(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            await db.commit()

        qdrant = StatefulFakeQdrant()

        # First 10 photos — identity A (dim 42)
        model_a = _fake_face_model(embedding_dim=42)
        for i in range(10):
            async with test_session_factory() as db:
                pa_id = await _seed_photo(db, ws, user_id, label=f"a{i}")
                await db.commit()
            async with test_session_factory() as db:
                await process_photo_for_faces(
                    pa_id, db, qdrant=qdrant, face_model=model_a
                )
                await db.commit()

        # Next 10 photos — identity B (dim 200 — orthogonal to 42)
        model_b = _fake_face_model(embedding_dim=200)
        for i in range(10):
            async with test_session_factory() as db:
                pa_id = await _seed_photo(db, ws, user_id, label=f"b{i}")
                await db.commit()
            async with test_session_factory() as db:
                await process_photo_for_faces(
                    pa_id, db, qdrant=qdrant, face_model=model_b
                )
                await db.commit()

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
        assert len(clusters) == 2
        member_counts = sorted(c.member_count for c in clusters)
        assert member_counts == [10, 10]
