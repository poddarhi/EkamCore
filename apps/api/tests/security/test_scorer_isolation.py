"""Workspace isolation for candidate scorer (S12-003).

Two workspaces, A and B. Workspace A has a cluster with 4 photos and
calendar events naming "Alice in A". Workspace B has a contact
"Alice B" with the same email as A's Alice. Scoring workspace A's
cluster must return ONLY contacts belonging to workspace A — even
though a same-email contact exists in B.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.auth import hash_password
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


async def _mk_workspace(db, suffix: str) -> tuple[UUID, UUID]:
    user = User(
        email=f"iso-{suffix}-{uuid4().hex[:6]}@ekamcore.dev",
        display_name=f"Iso {suffix}",
        password_hash=hash_password("pw-testpw-01234567"),
        role="standard",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    ws = Workspace(name=f"Iso {suffix}", type="personal", owner_id=user.id)
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin"))
    await db.flush()
    return ws.id, user.id


async def _seed_cluster_with_data(
    db, ws: UUID, uid: UUID, *, alice_name: str, alice_email: str
) -> UUID:
    src = Source(
        workspace_id=ws,
        name=f"iso-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=uid,
        status="active",
    )
    db.add(src)
    await db.flush()
    cluster = FaceCluster(
        workspace_id=ws,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=4,
        cluster_state="unconfirmed",
    )
    db.add(cluster)
    await db.flush()
    base = datetime(2026, 3, 1, 12, 0)
    base_aware = base.replace(tzinfo=timezone.utc)
    for i in range(4):
        f = File(
            workspace_id=ws,
            source_id=src.id,
            filename=f"ws-{i}.jpg",
            path=f"/tmp/{uuid4().hex}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10,
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(
            file_id=f.id, workspace_id=ws, face_count=1,
            taken_at=base + timedelta(days=i),
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
            cluster_id=cluster.id,
        )
        db.add(det)
        db.add(
            CalendarEvent(
                workspace_id=ws,
                source_id=src.id,
                external_id=uuid4().hex,
                title="Meet",
                start_at=base_aware + timedelta(days=i),
                end_at=base_aware + timedelta(days=i, hours=1),
                participants_json=[{"email": alice_email, "name": alice_name}],
            )
        )
    db.add(
        Contact(
            workspace_id=ws,
            source_id=src.id,
            external_id=uuid4().hex,
            first_name=alice_name.split()[0],
            last_name=alice_name.split()[-1],
            display_name=alice_name,
            emails_json=[{"address": alice_email}],
            imported_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return cluster.id


class TestScorerIsolation:
    async def test_workspace_a_never_surfaces_workspace_b_contacts(
        self, test_session_factory, face_env
    ):
        async with test_session_factory() as db:
            ws_a, uid_a = await _mk_workspace(db, "A")
            ws_b, uid_b = await _mk_workspace(db, "B")
            cluster_a = await _seed_cluster_with_data(
                db, ws_a, uid_a,
                alice_name="Alice A",
                alice_email="alice@example.com",
            )
            await _seed_cluster_with_data(
                db, ws_b, uid_b,
                alice_name="Alice B",
                alice_email="alice@example.com",
            )
            await db.commit()

        async with test_session_factory() as db:
            results = await score_cluster(cluster_a, db)

        assert len(results) >= 1
        returned_ids = [r.contact_id for r in results]

        # Every returned contact must live in workspace A.
        async with test_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(Contact.workspace_id).where(
                            Contact.id.in_(returned_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert all(w == ws_a for w in rows)
