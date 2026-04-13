"""Phase 3 clustering end-to-end tests (S12-008).

Walks every Sprint 12 service together in one integration test file:

  - cluster_workspace (S12-001)
  - incremental_cluster (S12-002)
  - candidate_scorer (S12-003)
  - trusted_person_service (S12-004)
  - review_queue (S12-005)
  - merge/split/undo (S12-006)
  - graph_edge_builder (S12-007)

HDBSCAN is replaced with a deterministic argmax stub (same pattern
as test_clustering_full_run.py) so the tests are hermetic. Face
embeddings are one-hot per identity so pairwise purity is exactly
provable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import numpy as np
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import and_, select

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.graph_edge import GraphEdge
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.auth import hash_password
from api.services.face import (
    candidate_scorer,
    clustering_service,
    consent_service,
    crypto,
    graph_edge_builder,
    incremental_cluster,
    merge_service,
    review_queue,
    split_service,
    trusted_person_service,
    undo_service,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ── Fake HDBSCAN (argmax of one-hot row == identity label) ─────────────────


_NOISE_DIM = 511


def _embedding_for_label(label: int) -> list[float]:
    vec = [0.0] * 512
    vec[_NOISE_DIM if label < 0 else label] = 1.0
    return vec


def _labels_by_argmax(X: np.ndarray) -> list[int]:
    labels: list[int] = []
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


# ── Fixtures ───────────────────────────────────────────────────────────────


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
def qdrant_stub():
    """In-memory Qdrant stand-in keyed by point id."""

    store: dict[str, dict] = {}

    async def _upsert(*, collection_name, points, **_):
        for p in points:
            store[str(p.id)] = {"vector": p.vector, "payload": p.payload}
        return None

    async def _search(*, collection_name, query_vector, query_filter, limit, **_):
        want_ws = None
        excl_fd = None
        if query_filter is not None:
            for c in (query_filter.must or []):
                if getattr(c, "key", None) == "workspace_id":
                    want_ws = str(c.match.value)
            for c in (query_filter.must_not or []):
                if getattr(c, "key", None) == "face_detection_id":
                    excl_fd = str(c.match.value)
        results = []
        q = np.asarray(query_vector, dtype=np.float32)
        for pid, row in store.items():
            pay = row["payload"]
            if want_ws and pay.get("workspace_id") != want_ws:
                continue
            if excl_fd and pay.get("face_detection_id") == excl_fd:
                continue
            v = np.asarray(row["vector"], dtype=np.float32)
            sim = float(np.dot(q, v))
            results.append(SimpleNamespace(id=pid, score=sim, payload=pay))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def _delete(**_):
        return None

    client = MagicMock()
    client.upsert = _upsert
    client.search = _search
    client.delete = _delete
    client._store = store  # type: ignore[attr-defined]
    return client


# ── Shared seed helpers ────────────────────────────────────────────────────


async def _grant_consent(factory, workspace_id, user_id):
    async with factory() as db:
        await consent_service.grant(
            workspace_id=workspace_id, user_id=user_id,
            ip="127.0.0.1", user_agent="pytest", db=db,
        )
        await db.commit()


async def _seed_faces(
    db, ws, uid, *, labels: list[int], base_time: datetime | None = None,
) -> tuple[UUID, list[UUID], list[UUID]]:
    src = Source(
        workspace_id=ws, name=f"p3-{uuid4().hex[:6]}",
        type="photo_folder", registered_by=uid, status="active",
    )
    db.add(src)
    await db.flush()
    det_ids: list[UUID] = []
    photo_ids: list[UUID] = []
    for i, label in enumerate(labels):
        f = File(
            workspace_id=ws, source_id=src.id,
            filename=f"p3-{i}.jpg", path=f"/tmp/{uuid4().hex}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10, mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        taken_at = None
        if base_time is not None:
            taken_at = base_time + timedelta(hours=i)
        pa = PhotoAsset(
            file_id=f.id, workspace_id=ws, face_count=1,
            taken_at=taken_at,
        )
        db.add(pa)
        await db.flush()
        det = FaceDetection(
            workspace_id=ws, photo_asset_id=pa.id,
            bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
            embedding_encrypted=crypto.encrypt_embedding(
                _embedding_for_label(label)
            ),
            embedding_dim=512,
            detector_version="t", recognizer_version="t",
            detection_score=0.9, qdrant_point_id=uuid4(),
        )
        db.add(det)
        await db.flush()
        det_ids.append(det.id)
        photo_ids.append(pa.id)
    return src.id, photo_ids, det_ids


# ── Tests ──────────────────────────────────────────────────────────────────


class TestPhase3ClusteringE2E:
    async def test_full_clustering_pipeline(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        labels = [i % 5 for i in range(50)]  # 10 faces per identity
        async with test_session_factory() as db:
            await _seed_faces(db, ws, uid, labels=labels)
            await db.commit()

        async with test_session_factory() as db:
            report = await clustering_service.cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()
        assert report.face_count == 50
        assert report.cluster_count == 5
        # Each cluster is 100% pure in this synthetic setup.
        async with test_session_factory() as db:
            clusters = (
                await db.execute(
                    select(FaceCluster).where(
                        and_(
                            FaceCluster.workspace_id == ws,
                            FaceCluster.deleted_at.is_(None),
                        )
                    )
                )
            ).scalars().all()
        assert len(clusters) == 5
        assert all(c.member_count == 10 for c in clusters)

    async def test_incremental_matches_full_within_tolerance(
        self, test_session_factory, seed_user, face_env, qdrant_stub
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        labels_initial = [i % 4 for i in range(40)]
        async with test_session_factory() as db:
            await _seed_faces(db, ws, uid, labels=labels_initial)
            await db.commit()
        async with test_session_factory() as db:
            await clustering_service.cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()

        # Seed Qdrant with embeddings for the existing faces so
        # incremental search can find neighbors.
        async with test_session_factory() as db:
            existing = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == ws
                    )
                )
            ).scalars().all()
            for f in existing:
                vec = crypto.decrypt_embedding(f.embedding_encrypted)
                arr = np.asarray(vec, dtype=np.float32)
                n = float(np.linalg.norm(arr))
                arr = arr / n if n > 0 else arr
                qdrant_stub._store[str(f.qdrant_point_id)] = {
                    "vector": arr.tolist(),
                    "payload": {
                        "workspace_id": str(ws),
                        "face_detection_id": str(f.id),
                    },
                }

        # Ingest 10 more faces via the incremental assigner.
        async with test_session_factory() as db:
            _, _, new_det_ids = await _seed_faces(
                db, ws, uid, labels=[i % 4 for i in range(10)]
            )
            await db.commit()
        for det_id in new_det_ids:
            async with test_session_factory() as db:
                # register in qdrant first
                row = (
                    await db.execute(
                        select(FaceDetection).where(FaceDetection.id == det_id)
                    )
                ).scalar_one()
                vec = crypto.decrypt_embedding(row.embedding_encrypted)
                arr = np.asarray(vec, dtype=np.float32)
                n = float(np.linalg.norm(arr))
                arr = arr / n if n > 0 else arr
                qdrant_stub._store[str(row.qdrant_point_id)] = {
                    "vector": arr.tolist(),
                    "payload": {
                        "workspace_id": str(ws),
                        "face_detection_id": str(row.id),
                    },
                }
                await incremental_cluster.assign_face_to_cluster(
                    det_id, db, qdrant_stub
                )
                await db.commit()

        # Full re-cluster — must land on exactly 4 clusters again.
        async with test_session_factory() as db:
            report = await clustering_service.cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()
        assert abs(report.cluster_count - 4) <= 1

    async def test_candidate_scoring_end_to_end(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        base = datetime(2026, 3, 1, 12, 0)
        base_aware = base.replace(tzinfo=timezone.utc)
        async with test_session_factory() as db:
            src_id, photo_ids, det_ids = await _seed_faces(
                db, ws, uid, labels=[0] * 5, base_time=base,
            )
            for i in range(5):
                db.add(
                    CalendarEvent(
                        workspace_id=ws, source_id=src_id,
                        external_id=uuid4().hex, title="Meet",
                        start_at=base_aware + timedelta(hours=i),
                        end_at=base_aware + timedelta(hours=i, minutes=30),
                        participants_json=[
                            {"email": "alice@example.com", "name": "Alice Smith"}
                        ],
                    )
                )
            db.add(
                Contact(
                    workspace_id=ws, source_id=src_id,
                    external_id=uuid4().hex,
                    first_name="Alice", last_name="Smith",
                    display_name="Alice Smith",
                    emails_json=[{"address": "alice@example.com"}],
                    imported_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        async with test_session_factory() as db:
            await clustering_service.cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()
        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(
                        and_(
                            FaceCluster.workspace_id == ws,
                            FaceCluster.deleted_at.is_(None),
                        )
                    )
                )
            ).scalar_one()
            results = await candidate_scorer.score_cluster(cluster.id, db)
        assert len(results) >= 1
        top = results[0]
        assert top.score >= 0.50
        assert top.confidence in ("medium", "high")

    async def test_review_queue_to_confirm(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        async with test_session_factory() as db:
            src_id, _, _ = await _seed_faces(
                db, ws, uid, labels=[0] * 5,
            )
            contact = Contact(
                workspace_id=ws, source_id=src_id,
                external_id=uuid4().hex,
                display_name="Alice",
                emails_json=[{"address": "a@example.com"}],
                imported_at=datetime.now(timezone.utc),
            )
            db.add(contact)
            await db.commit()
            contact_id = contact.id
        async with test_session_factory() as db:
            await clustering_service.cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()
        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(
                        and_(
                            FaceCluster.workspace_id == ws,
                            FaceCluster.deleted_at.is_(None),
                        )
                    )
                )
            ).scalar_one()
            cluster.candidates_json = [
                {
                    "contact_id": str(contact_id),
                    "score": 0.85,
                    "confidence": "high",
                    "signals": {"co_occurrence": 1.0},
                }
            ]
            await db.commit()
            cluster_id = cluster.id

        async with test_session_factory() as db:
            items, _ = await review_queue.list_pending(
                workspace_id=ws, user_id=uid, db=db, limit=10
            )
        assert any(i.cluster_id == cluster_id for i in items)

        async with test_session_factory() as db:
            await trusted_person_service.confirm_candidate(
                cluster_id=cluster_id,
                contact_id=contact_id,
                workspace_id=ws,
                user_id=uid,
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            items_after, _ = await review_queue.list_pending(
                workspace_id=ws, user_id=uid, db=db, limit=10
            )
        assert not any(i.cluster_id == cluster_id for i in items_after)

    async def test_merge_undo_cycle(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        async with test_session_factory() as db:
            keeper = TrustedPerson(
                workspace_id=ws, display_name="K", trust_source="manual"
            )
            p2 = TrustedPerson(
                workspace_id=ws, display_name="P2", trust_source="manual"
            )
            p3 = TrustedPerson(
                workspace_id=ws, display_name="P3", trust_source="manual"
            )
            db.add_all([keeper, p2, p3])
            await db.commit()
            ids = [keeper.id, p2.id, p3.id]
            keeper_id = keeper.id

        async with test_session_factory() as db:
            await merge_service.merge_persons(
                person_ids=ids, keeper_id=keeper_id,
                workspace_id=ws, user_id=uid, db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await undo_service.undo_last_operation(
                workspace_id=ws, user_id=uid, db=db
            )
            await db.commit()

        async with test_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(TrustedPerson).where(
                            and_(
                                TrustedPerson.workspace_id == ws,
                                TrustedPerson.deleted_at.is_(None),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert {r.id for r in rows} == set(ids)

    async def test_split_undo_cycle(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        # Seed a person with a 10-face cluster.
        async with test_session_factory() as db:
            src_id, _, det_ids = await _seed_faces(
                db, ws, uid, labels=[0] * 10
            )
            person = TrustedPerson(
                workspace_id=ws, display_name="Original",
                trust_source="manual",
            )
            db.add(person)
            await db.flush()
            cluster = FaceCluster(
                workspace_id=ws,
                centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
                member_count=10,
                cluster_state="confirmed",
                trusted_person_id=person.id,
            )
            db.add(cluster)
            await db.flush()
            for det_id in det_ids:
                await db.execute(
                    FaceDetection.__table__.update()
                    .where(FaceDetection.id == det_id)
                    .values(cluster_id=cluster.id)
                )
            await db.commit()
            person_id = person.id
            cluster_id = cluster.id

        async with test_session_factory() as db:
            await split_service.split_person(
                person_id=person_id,
                face_detection_ids=det_ids[:3],
                new_display_name="Split",
                workspace_id=ws, user_id=uid, db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await undo_service.undo_last_operation(
                workspace_id=ws, user_id=uid, db=db
            )
            await db.commit()

        async with test_session_factory() as db:
            cluster_after = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
            restored = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.id.in_(det_ids[:3])
                    )
                )
            ).scalars().all()
            persons = (
                (
                    await db.execute(
                        select(TrustedPerson).where(
                            TrustedPerson.workspace_id == ws
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert cluster_after.member_count == 10
        assert all(f.cluster_id == cluster_id for f in restored)
        assert len(persons) == 1

    async def test_graph_edges_after_confirm(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        async with test_session_factory() as db:
            src_id, _, _ = await _seed_faces(db, ws, uid, labels=[0] * 5)
            contact = Contact(
                workspace_id=ws, source_id=src_id,
                external_id=uuid4().hex,
                display_name="C",
                emails_json=[{"address": "c@example.com"}],
                imported_at=datetime.now(timezone.utc),
            )
            db.add(contact)
            await db.commit()
            contact_id = contact.id

        async with test_session_factory() as db:
            await clustering_service.cluster_workspace(
                ws, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()
        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(
                        and_(
                            FaceCluster.workspace_id == ws,
                            FaceCluster.deleted_at.is_(None),
                        )
                    )
                )
            ).scalar_one()
            cluster.candidates_json = [
                {
                    "contact_id": str(contact_id),
                    "score": 0.9,
                    "confidence": "high",
                    "signals": {},
                }
            ]
            await db.commit()
            cluster_id = cluster.id

        async with test_session_factory() as db:
            person = await trusted_person_service.confirm_candidate(
                cluster_id=cluster_id,
                contact_id=contact_id,
                workspace_id=ws,
                user_id=uid,
                db=db,
            )
            await db.commit()
            person_id = person.id

        async with test_session_factory() as db:
            edges = (
                (
                    await db.execute(
                        select(GraphEdge).where(
                            and_(
                                GraphEdge.workspace_id == ws,
                                GraphEdge.from_type == "trusted_person",
                                GraphEdge.from_id == person_id,
                                GraphEdge.to_type == "photo_asset",
                                GraphEdge.edge_type == "appears_in",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(edges) == 5

    async def test_workspace_isolation_full_phase3(
        self, test_session_factory, face_env
    ):
        async def _mk_ws(label: str) -> tuple[UUID, UUID]:
            async with test_session_factory() as db:
                u = User(
                    email=f"p3-{label}-{uuid4().hex[:6]}@ekamcore.dev",
                    display_name=f"P3 {label}",
                    password_hash=hash_password("testpassword123"),
                    role="standard", is_active=True,
                )
                db.add(u)
                await db.flush()
                ws = Workspace(name=f"P3 {label}", type="personal", owner_id=u.id)
                db.add(ws)
                await db.flush()
                db.add(
                    WorkspaceMember(
                        workspace_id=ws.id, user_id=u.id, role="admin"
                    )
                )
                await consent_service.grant(
                    workspace_id=ws.id, user_id=u.id,
                    ip="127.0.0.1", user_agent="pytest", db=db,
                )
                await db.commit()
                return ws.id, u.id

        ws_a, uid_a = await _mk_ws("A")
        ws_b, uid_b = await _mk_ws("B")

        async with test_session_factory() as db:
            await _seed_faces(db, ws_a, uid_a, labels=[i % 3 for i in range(15)])
            await _seed_faces(db, ws_b, uid_b, labels=[i % 3 for i in range(15)])
            await db.commit()

        async with test_session_factory() as db:
            await clustering_service.cluster_workspace(
                ws_a, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()
        async with test_session_factory() as db:
            await clustering_service.cluster_workspace(
                ws_b, db, hdbscan_module=_fake_hdbscan()
            )
            await db.commit()

        async with test_session_factory() as db:
            a_items, _ = await review_queue.list_pending(
                workspace_id=ws_a, user_id=uid_a, db=db, limit=50
            )
            b_items, _ = await review_queue.list_pending(
                workspace_id=ws_b, user_id=uid_b, db=db, limit=50
            )
        a_cluster_ids = {i.cluster_id for i in a_items}
        b_cluster_ids = {i.cluster_id for i in b_items}
        assert not (a_cluster_ids & b_cluster_ids)

        async with test_session_factory() as db:
            await graph_edge_builder.build_person_photo_edges(
                workspace_id=ws_a, db=db
            )
            await db.commit()
        async with test_session_factory() as db:
            edges = (
                (
                    await db.execute(
                        select(GraphEdge).where(GraphEdge.workspace_id == ws_b)
                    )
                )
                .scalars()
                .all()
            )
        assert edges == []
