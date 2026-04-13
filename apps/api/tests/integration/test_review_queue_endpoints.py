"""Integration tests for /api/v1/review-queue endpoints (S12-005)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
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


async def _seed_cluster(factory, ws, uid, *, score: float):
    async with factory() as db:
        src = Source(
            workspace_id=ws,
            name=f"rqe-{uuid4().hex[:6]}",
            type="photo_folder",
            registered_by=uid,
            status="active",
        )
        db.add(src)
        await db.flush()
        contact_id = uuid4()
        cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=5,
            cluster_state="unconfirmed",
            candidates_json=[
                {
                    "contact_id": str(contact_id),
                    "score": score,
                    "confidence": "high" if score >= 0.75 else "medium",
                    "signals": {"co_occurrence": score},
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
                filename=f"rqe-{i}.jpg",
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
            await db.flush()
        cluster_id = cluster.id
        await db.commit()
    return cluster_id


async def _grant(factory, ws, uid):
    async with factory() as db:
        await consent_service.grant(
            workspace_id=ws, user_id=uid,
            ip="127.0.0.1", user_agent="pytest", db=db,
        )
        await db.commit()


def _h(tokens, *, csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    if csrf:
        h["X-CSRF-Token"] = tokens["csrf_token"]
    return h


def _c(tokens) -> dict:
    return {"ekamcore_csrf": tokens["csrf_token"]}


class TestReviewQueueEndpoints:
    async def test_list_returns_items_sorted_by_score(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        low_id = await _seed_cluster(test_session_factory, ws, uid, score=0.55)
        high_id = await _seed_cluster(test_session_factory, ws, uid, score=0.90)

        resp = await client.get(_URL, headers=_h(auth_tokens))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [i["cluster_id"] for i in body["items"]]
        assert ids[:2] == [str(high_id), str(low_id)]
        assert body["items"][0]["confidence_bucket"] == "high"

    async def test_get_detail_lists_all_members(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        cluster_id = await _seed_cluster(
            test_session_factory, ws, uid, score=0.8
        )
        resp = await client.get(
            f"{_URL}/{cluster_id}", headers=_h(auth_tokens)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["member_count"] == 5
        assert len(body["face_detection_ids"]) == 5
        assert len(body["photo_asset_ids"]) == 5

    async def test_skip_excludes_cluster_from_subsequent_list(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        cluster_id = await _seed_cluster(
            test_session_factory, ws, uid, score=0.8
        )

        resp = await client.post(
            f"{_URL}/{cluster_id}/skip",
            headers=_h(auth_tokens, csrf=True),
            cookies=_c(auth_tokens),
        )
        assert resp.status_code == 204, resp.text

        resp = await client.get(_URL, headers=_h(auth_tokens))
        assert resp.status_code == 200
        ids = [i["cluster_id"] for i in resp.json()["items"]]
        assert str(cluster_id) not in ids

    async def test_missing_consent_returns_403(
        self, client, auth_tokens, face_env
    ):
        resp = await client.get(_URL, headers=_h(auth_tokens))
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"
