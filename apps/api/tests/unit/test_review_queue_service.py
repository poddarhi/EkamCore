"""Unit tests for review_queue service (S12-005)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.services import flags
from api.services.face import crypto, review_queue

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


@pytest.fixture
def stub_redis():
    """Non-persistent in-memory Redis stand-in for the skip marker."""
    store: dict[str, str] = {}

    async def _get(key):
        return store.get(key)

    async def _set(key, value, ex=None):
        store[key] = value
        return True

    async def _delete(key):
        store.pop(key, None)
        return 1

    class _Pipe:
        def incr(self, *_):
            return self

        def expire(self, *_):
            return self

        async def execute(self):
            return [1, True]

    r = AsyncMock()
    r.get = AsyncMock(side_effect=_get)
    r.set = AsyncMock(side_effect=_set)
    r.delete = AsyncMock(side_effect=_delete)
    r.pipeline = lambda transaction=False: _Pipe()
    r._store = store  # type: ignore[attr-defined]
    with patch(
        "api.services.face.review_queue.get_redis", return_value=r
    ):
        yield r


async def _mk_source(db, ws, uid) -> UUID:
    src = Source(
        workspace_id=ws,
        name=f"rq-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=uid,
        status="active",
    )
    db.add(src)
    await db.flush()
    return src.id


async def _mk_cluster_with_members(
    db, ws, uid, src_id, *,
    member_count: int,
    top_score: float,
    cluster_state: str = "unconfirmed",
    trusted_person_id: UUID | None = None,
    base_time: datetime,
) -> UUID:
    contact_id = uuid4()
    cluster = FaceCluster(
        workspace_id=ws,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=member_count,
        cluster_state=cluster_state,
        trusted_person_id=trusted_person_id,
        candidates_json=(
            [
                {
                    "contact_id": str(contact_id),
                    "score": top_score,
                    "confidence": (
                        "high"
                        if top_score >= 0.75
                        else "medium"
                        if top_score >= 0.50
                        else "low"
                    ),
                    "signals": {"co_occurrence": top_score},
                }
            ]
            if top_score > 0
            else None
        ),
    )
    db.add(cluster)
    await db.flush()
    for i in range(member_count):
        f = File(
            workspace_id=ws,
            source_id=src_id,
            filename=f"rq-{uuid4().hex[:6]}.jpg",
            path=f"/tmp/{uuid4().hex}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10,
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(
            file_id=f.id,
            workspace_id=ws,
            face_count=1,
            taken_at=base_time + timedelta(days=i),
        )
        db.add(pa)
        await db.flush()
        det = FaceDetection(
            workspace_id=ws,
            photo_asset_id=pa.id,
            bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
            embedding_encrypted=crypto.encrypt_embedding([0.0] * 512),
            embedding_dim=512,
            detector_version="t",
            recognizer_version="t",
            detection_score=0.9 - (i * 0.01),
            qdrant_point_id=uuid4(),
            cluster_id=cluster.id,
        )
        db.add(det)
        await db.flush()
    return cluster.id


class TestReviewQueueService:
    async def test_list_pending_orders_by_score_and_paginates(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1, tzinfo=timezone.utc).replace(tzinfo=None)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            cluster_ids_by_score: dict[float, UUID] = {}
            for i, score in enumerate([0.90, 0.80, 0.60, 0.40, 0.20]):
                cid = await _mk_cluster_with_members(
                    db, ws, uid, src,
                    member_count=5,
                    top_score=score,
                    base_time=base + timedelta(hours=i),
                )
                cluster_ids_by_score[score] = cid
            await db.commit()

        async with test_session_factory() as db:
            page1, cursor1 = await review_queue.list_pending(
                workspace_id=ws, user_id=uid, db=db, limit=2
            )
        assert [i.cluster_id for i in page1] == [
            cluster_ids_by_score[0.90],
            cluster_ids_by_score[0.80],
        ]
        assert cursor1 is not None
        # Items include member counts and first/last seen.
        assert page1[0].member_count == 5
        assert page1[0].first_seen_at is not None
        assert page1[0].last_seen_at is not None
        # Only up to 6 sample face detections surfaced.
        assert len(page1[0].sample_face_detection_ids) <= 6
        assert len(page1[0].sample_face_detection_ids) == len(
            page1[0].sample_photo_asset_ids
        )

        async with test_session_factory() as db:
            page2, cursor2 = await review_queue.list_pending(
                workspace_id=ws, user_id=uid, db=db, limit=2, cursor=cursor1
            )
        assert [i.cluster_id for i in page2] == [
            cluster_ids_by_score[0.60],
            cluster_ids_by_score[0.40],
        ]
        assert cursor2 is not None

    async def test_list_pending_excludes_small_and_confirmed(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            # Too small — below default min_cluster_size=3
            await _mk_cluster_with_members(
                db, ws, uid, src,
                member_count=2,
                top_score=0.9,
                base_time=base,
            )
            # Confirmed — has trusted_person_id
            person = TrustedPerson(
                workspace_id=ws,
                display_name="Already Labelled",
                trust_source="manual",
            )
            db.add(person)
            await db.flush()
            await _mk_cluster_with_members(
                db, ws, uid, src,
                member_count=5,
                top_score=0.9,
                cluster_state="confirmed",
                trusted_person_id=person.id,
                base_time=base + timedelta(days=1),
            )
            # Eligible
            eligible_id = await _mk_cluster_with_members(
                db, ws, uid, src,
                member_count=5,
                top_score=0.7,
                base_time=base + timedelta(days=2),
            )
            await db.commit()

        async with test_session_factory() as db:
            items, _ = await review_queue.list_pending(
                workspace_id=ws, user_id=uid, db=db, limit=10
            )
        assert [i.cluster_id for i in items] == [eligible_id]

    async def test_confidence_filter(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            high_id = await _mk_cluster_with_members(
                db, ws, uid, src,
                member_count=5, top_score=0.85,
                base_time=base,
            )
            await _mk_cluster_with_members(
                db, ws, uid, src,
                member_count=5, top_score=0.60,
                base_time=base + timedelta(days=1),
            )
            await _mk_cluster_with_members(
                db, ws, uid, src,
                member_count=5, top_score=0.30,
                base_time=base + timedelta(days=2),
            )
            await db.commit()

        async with test_session_factory() as db:
            high_items, _ = await review_queue.list_pending(
                workspace_id=ws, user_id=uid, db=db,
                limit=10, confidence_filter="high",
            )
        assert [i.cluster_id for i in high_items] == [high_id]
        assert high_items[0].confidence_bucket == "high"

    async def test_skip_marker_excludes_for_same_user_only(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        ws = seed_user["workspace_id"]
        uid_a = seed_user["user_id"]
        uid_b = uuid4()  # a hypothetical second reviewer
        base = datetime(2026, 3, 1)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid_a)
            cluster_id = await _mk_cluster_with_members(
                db, ws, uid_a, src,
                member_count=5, top_score=0.8,
                base_time=base,
            )
            await db.commit()

        async with test_session_factory() as db:
            await review_queue.skip(
                cluster_id=cluster_id,
                workspace_id=ws,
                user_id=uid_a,
                db=db,
            )

        async with test_session_factory() as db:
            a_items, _ = await review_queue.list_pending(
                workspace_id=ws, user_id=uid_a, db=db, limit=10
            )
            b_items, _ = await review_queue.list_pending(
                workspace_id=ws, user_id=uid_b, db=db, limit=10
            )
        assert cluster_id not in [i.cluster_id for i in a_items]
        assert cluster_id in [i.cluster_id for i in b_items]

    async def test_get_item_returns_all_members(
        self, test_session_factory, seed_user, face_env, stub_redis
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1)

        async with test_session_factory() as db:
            src = await _mk_source(db, ws, uid)
            cluster_id = await _mk_cluster_with_members(
                db, ws, uid, src,
                member_count=8, top_score=0.9,
                base_time=base,
            )
            await db.commit()

        async with test_session_factory() as db:
            detail = await review_queue.get_item(
                cluster_id=cluster_id, workspace_id=ws, db=db
            )
        assert detail.member_count == 8
        assert len(detail.face_detection_ids) == 8
        assert len(detail.photo_asset_ids) == 8
        assert detail.top_candidate is not None
        assert detail.top_candidate.score == pytest.approx(0.9)
