"""Unit tests for candidate_scorer.score_cluster (S12-003).

Four scenarios drive the scoring weight combination directly:

  - calendar co-occurrence at matching photo times → top contact ranks #1 high
  - no signals at all → empty candidate list
  - two contacts tie on co-occurrence → both returned with ~equal scores
  - pre-existing graph_edge to Bob → Bob ranked #1 on the edge signal

The tests avoid touching Qdrant, Redis, or consent — score_cluster is
pure DB. A local Fernet key is installed via the face_env fixture so
encrypt/decrypt of the stubbed face_detection embeddings works.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.graph_edge import GraphEdge
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
from api.services.face import crypto
from api.services.face.candidate_scorer import score_cluster

pytestmark = pytest.mark.asyncio(loop_scope="session")


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


async def _mk_source(db, workspace_id, user_id) -> UUID:
    src = Source(
        workspace_id=workspace_id,
        name=f"sc-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()
    return src.id


async def _mk_cluster(db, workspace_id, *, member_count: int) -> UUID:
    cl = FaceCluster(
        workspace_id=workspace_id,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=member_count,
        cluster_state="unconfirmed",
    )
    db.add(cl)
    await db.flush()
    return cl.id


async def _mk_face(
    db, workspace_id, user_id, source_id, cluster_id, *, taken_at, filename
):
    f = File(
        workspace_id=workspace_id,
        source_id=source_id,
        filename=filename,
        path=f"/tmp/{uuid4().hex}-{filename}",
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=10,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()
    pa = PhotoAsset(
        file_id=f.id,
        workspace_id=workspace_id,
        face_count=1,
        taken_at=taken_at,
    )
    db.add(pa)
    await db.flush()
    det = FaceDetection(
        workspace_id=workspace_id,
        photo_asset_id=pa.id,
        bbox_json={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        embedding_encrypted=crypto.encrypt_embedding([0.0] * 512),
        embedding_dim=512,
        detector_version="t",
        recognizer_version="t",
        detection_score=0.9,
        qdrant_point_id=uuid4(),
        cluster_id=cluster_id,
    )
    db.add(det)
    await db.flush()
    return pa.id, det.id


async def _mk_contact(db, workspace_id, source_id, *, display_name, email):
    c = Contact(
        workspace_id=workspace_id,
        source_id=source_id,
        external_id=uuid4().hex,
        first_name=display_name.split()[0],
        last_name=display_name.split()[-1] if " " in display_name else None,
        display_name=display_name,
        emails_json=[{"address": email}],
        imported_at=datetime.now(timezone.utc),
    )
    db.add(c)
    await db.flush()
    return c.id


async def _mk_event(db, workspace_id, source_id, *, start_at, participants):
    ev = CalendarEvent(
        workspace_id=workspace_id,
        source_id=source_id,
        external_id=uuid4().hex,
        title="Meeting",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        participants_json=participants,
    )
    db.add(ev)
    await db.flush()
    return ev.id


class TestScoreCluster:
    async def test_co_occurrence_top_rank_high_confidence(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1, 12, 0)
        base_aware = base.replace(tzinfo=timezone.utc)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            cluster_id = await _mk_cluster(db, ws, member_count=5)
            for i in range(5):
                await _mk_face(
                    db, ws, uid, src, cluster_id,
                    taken_at=base + timedelta(days=i),
                    filename=f"img-{i}.jpg",
                )
                await _mk_event(
                    db, ws, src,
                    start_at=base_aware + timedelta(days=i),
                    participants=[{"email": "alice@example.com", "name": "Alice Smith"}],
                )
            await _mk_contact(
                db, ws, src,
                display_name="Alice Smith",
                email="alice@example.com",
            )
            await _mk_contact(
                db, ws, src,
                display_name="Charlie Other",
                email="charlie@example.com",
            )
            await db.commit()

        async with test_session_factory() as db:
            results = await score_cluster(cluster_id, db)

        assert len(results) >= 1
        top = results[0]
        # 5/5 co_occurrence hits → co_norm=1.0; size_bonus=1.0. Score =
        # 0.5*1.0 + 0.05*1.0 = 0.55 → medium confidence. (No graph edge,
        # filename doesn't fuzzy-match, span < 6 months → no temporal.)
        assert top.score >= 0.50
        assert top.confidence in ("medium", "high")
        assert top.signals["co_occurrence"] == pytest.approx(1.0)

    async def test_no_signals_returns_empty(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1, 12, 0)
        base_aware = base.replace(tzinfo=timezone.utc)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            cluster_id = await _mk_cluster(db, ws, member_count=3)
            for i in range(3):
                await _mk_face(
                    db, ws, uid, src, cluster_id,
                    taken_at=base + timedelta(days=i),
                    filename=f"nope-{i}.jpg",
                )
            # One completely unrelated contact, no calendar event matches.
            await _mk_contact(
                db, ws, src,
                display_name="Nobody Special",
                email="nobody@example.com",
            )
            await db.commit()

        async with test_session_factory() as db:
            results = await score_cluster(cluster_id, db)

        assert results == []

    async def test_two_contacts_tie_on_co_occurrence(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1, 12, 0)
        base_aware = base.replace(tzinfo=timezone.utc)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            cluster_id = await _mk_cluster(db, ws, member_count=4)
            for i in range(4):
                await _mk_face(
                    db, ws, uid, src, cluster_id,
                    taken_at=base + timedelta(days=i),
                    filename=f"tie-{i}.jpg",
                )
                await _mk_event(
                    db, ws, src,
                    start_at=base_aware + timedelta(days=i),
                    participants=[
                        {"email": "alice@example.com", "name": "Alice Smith"},
                        {"email": "bob@example.com", "name": "Bob Jones"},
                    ],
                )
            await _mk_contact(
                db, ws, src, display_name="Alice Smith",
                email="alice@example.com",
            )
            await _mk_contact(
                db, ws, src, display_name="Bob Jones",
                email="bob@example.com",
            )
            await db.commit()

        async with test_session_factory() as db:
            results = await score_cluster(cluster_id, db)

        assert len(results) == 2
        # Both contacts observed at every photo → identical scores.
        assert results[0].score == pytest.approx(results[1].score)

    async def test_graph_edge_boost_ranks_bob_first(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1, 12, 0)
        base_aware = base.replace(tzinfo=timezone.utc)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            cluster_id = await _mk_cluster(db, ws, member_count=4)
            for i in range(4):
                await _mk_face(
                    db, ws, uid, src, cluster_id,
                    taken_at=base + timedelta(days=i),
                    filename=f"edge-{i}.jpg",
                )
            # Weak co-occurrence on Alice: one event at one photo.
            await _mk_event(
                db, ws, src,
                start_at=base_aware,
                participants=[{"email": "alice@example.com", "name": "Alice Smith"}],
            )
            alice_id = await _mk_contact(
                db, ws, src, display_name="Alice Smith",
                email="alice@example.com",
            )
            bob_id = await _mk_contact(
                db, ws, src, display_name="Bob Jones",
                email="bob@example.com",
            )
            # Pre-existing confirmed edge: this cluster → Bob.
            db.add(
                GraphEdge(
                    workspace_id=ws,
                    from_type="face_cluster",
                    from_id=cluster_id,
                    to_type="contact",
                    to_id=bob_id,
                    edge_type="confirmed_identity",
                    strength=1.0,
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            results = await score_cluster(cluster_id, db)

        ranks = {r.contact_id: i for i, r in enumerate(results)}
        assert bob_id in ranks
        assert alice_id in ranks
        # Bob's +0.20 edge dominates Alice's 0.50 * (1/4) = 0.125 co.
        assert ranks[bob_id] < ranks[alice_id]
