"""Workspace isolation for /api/v1/review-queue (S12-005)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

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
from api.services.face import consent_service, crypto

pytestmark = pytest.mark.asyncio(loop_scope="session")

_URL = "/api/v1/review-queue"


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


async def _mk_user_and_ws(factory, label: str) -> tuple[UUID, UUID, str]:
    email = f"rqiso-{label}-{uuid4().hex[:6]}@ekamcore.dev"
    async with factory() as db:
        u = User(
            email=email,
            display_name=f"RQIso {label}",
            password_hash=hash_password("testpassword123"),
            role="standard",
            is_active=True,
        )
        db.add(u)
        await db.flush()
        ws = Workspace(name=f"RQIso {label}", type="personal", owner_id=u.id)
        db.add(ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role="admin"))
        await consent_service.grant(
            workspace_id=ws.id,
            user_id=u.id,
            ip="127.0.0.1",
            user_agent="pytest",
            db=db,
        )
        await db.commit()
        return u.id, ws.id, email


async def _seed_cluster(factory, ws, uid) -> UUID:
    async with factory() as db:
        src = Source(
            workspace_id=ws,
            name=f"rqi-{uuid4().hex[:6]}",
            type="photo_folder",
            registered_by=uid,
            status="active",
        )
        db.add(src)
        await db.flush()
        cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=5,
            cluster_state="unconfirmed",
            candidates_json=[
                {
                    "contact_id": str(uuid4()),
                    "score": 0.9,
                    "confidence": "high",
                    "signals": {},
                }
            ],
        )
        db.add(cluster)
        await db.flush()
        base = datetime(2026, 3, 1, 12, 0)
        for i in range(5):
            f = File(
                workspace_id=ws,
                source_id=src.id,
                filename=f"rqi-{i}.jpg",
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
                taken_at=base + timedelta(days=i),
            )
            db.add(pa)
            await db.flush()
            db.add(
                FaceDetection(
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
            )
        cluster_id = cluster.id
        await db.commit()
    return cluster_id


async def _login(client, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpassword123"},
    )
    assert resp.status_code == 200, resp.text
    return {
        "access_token": resp.json()["access_token"],
        "csrf_token": resp.cookies.get("ekamcore_csrf"),
    }


def _h(tokens, *, csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    if csrf:
        h["X-CSRF-Token"] = tokens["csrf_token"]
    return h


def _c(tokens) -> dict:
    return {"ekamcore_csrf": tokens["csrf_token"]}


class TestReviewQueueIsolation:
    async def test_user_a_never_sees_workspace_b_clusters(
        self, client, test_session_factory, face_env
    ):
        uid_a, ws_a, email_a = await _mk_user_and_ws(test_session_factory, "A")
        uid_b, ws_b, email_b = await _mk_user_and_ws(test_session_factory, "B")
        cluster_a = await _seed_cluster(test_session_factory, ws_a, uid_a)
        cluster_b = await _seed_cluster(test_session_factory, ws_b, uid_b)

        tokens_a = await _login(client, email_a)

        # List should contain only A's cluster.
        resp = await client.get(_URL, headers=_h(tokens_a))
        assert resp.status_code == 200, resp.text
        ids = {i["cluster_id"] for i in resp.json()["items"]}
        assert str(cluster_a) in ids
        assert str(cluster_b) not in ids

        # Detail on B's cluster → 404 (don't leak existence).
        resp = await client.get(
            f"{_URL}/{cluster_b}", headers=_h(tokens_a)
        )
        assert resp.status_code == 404

        # Skipping B's cluster must also 404 — a confused-deputy
        # attempt should not pollute A's skip set.
        resp = await client.post(
            f"{_URL}/{cluster_b}/skip",
            headers=_h(tokens_a, csrf=True),
            cookies=_c(tokens_a),
        )
        assert resp.status_code == 404
