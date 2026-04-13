"""Integration test for score_workspace_clusters (S12-003).

Seeds a workspace with:
  - 2 face clusters — one with 5 members, one with 1 member (below floor)
  - Matching photos + calendar events for the larger cluster (Alice)
  - One unrelated contact

Runs ``score_workspace_clusters`` and asserts:
  - Scored cluster row has ``candidates_json`` populated with Alice on top
  - Small cluster is counted in ``skipped_small`` and its candidates_json
    remains NULL
  - An audit_log row ``face_candidates_scored`` is written with counts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import and_, select

from api.db.models.audit_log import AuditLog
from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
from api.services.face import consent_service, crypto
from api.services.face.candidate_scorer import score_workspace_clusters

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


async def _seed_face(db, ws, uid, src_id, cluster_id, *, taken_at, filename):
    f = File(
        workspace_id=ws,
        source_id=src_id,
        filename=filename,
        path=f"/tmp/{uuid4().hex}-{filename}",
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=10,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()
    pa = PhotoAsset(
        file_id=f.id, workspace_id=ws, face_count=1, taken_at=taken_at
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
        detection_score=0.9,
        qdrant_point_id=uuid4(),
        cluster_id=cluster_id,
    )
    db.add(det)
    await db.flush()


class TestCandidateScoringBatch:
    async def test_batch_populates_candidates_json(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        base = datetime(2026, 3, 1, 12, 0)
        base_aware = base.replace(tzinfo=timezone.utc)

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws,
                user_id=uid,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            src = Source(
                workspace_id=ws,
                name=f"bscore-{uuid4().hex[:6]}",
                type="photo_folder",
                registered_by=uid,
                status="active",
            )
            db.add(src)
            await db.flush()

            # Big cluster with 5 photos and Alice at every event.
            big = FaceCluster(
                workspace_id=ws,
                centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
                member_count=5,
                cluster_state="unconfirmed",
            )
            db.add(big)
            await db.flush()
            for i in range(5):
                await _seed_face(
                    db, ws, uid, src.id, big.id,
                    taken_at=base + timedelta(days=i),
                    filename=f"big-{i}.jpg",
                )
                db.add(
                    CalendarEvent(
                        workspace_id=ws,
                        source_id=src.id,
                        external_id=uuid4().hex,
                        title="Lunch",
                        start_at=base_aware + timedelta(days=i),
                        end_at=base_aware + timedelta(days=i, hours=1),
                        participants_json=[
                            {"email": "alice@example.com", "name": "Alice Smith"}
                        ],
                    )
                )

            # Small cluster: only 1 member → below floor.
            small = FaceCluster(
                workspace_id=ws,
                centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
                member_count=1,
                cluster_state="unconfirmed",
            )
            db.add(small)
            await db.flush()
            await _seed_face(
                db, ws, uid, src.id, small.id,
                taken_at=base,
                filename="small.jpg",
            )

            alice = Contact(
                workspace_id=ws,
                source_id=src.id,
                external_id=uuid4().hex,
                first_name="Alice",
                last_name="Smith",
                display_name="Alice Smith",
                emails_json=[{"address": "alice@example.com"}],
                imported_at=datetime.now(timezone.utc),
            )
            db.add(alice)
            await db.commit()
            big_id = big.id
            small_id = small.id
            alice_id = alice.id

        async with test_session_factory() as db:
            report = await score_workspace_clusters(ws, db)
            await db.commit()

        assert report.scored_clusters == 1
        assert report.skipped_small == 1
        assert report.total_candidates_written >= 1

        async with test_session_factory() as db:
            big_row = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == big_id)
                )
            ).scalar_one()
            small_row = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == small_id)
                )
            ).scalar_one()
            audit_rows = (
                (
                    await db.execute(
                        select(AuditLog).where(
                            and_(
                                AuditLog.workspace_id == ws,
                                AuditLog.action == "face_candidates_scored",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert big_row.candidates_json is not None
        assert len(big_row.candidates_json) >= 1
        assert big_row.candidates_json[0]["contact_id"] == str(alice_id)
        assert small_row.candidates_json is None
        assert len(audit_rows) >= 1
        meta = audit_rows[-1].metadata_json or {}
        assert meta.get("scored_clusters") == 1
        assert meta.get("skipped_small") == 1
