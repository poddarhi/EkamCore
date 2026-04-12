"""Integration tests for GET /api/v1/face/status (S11-008).

Verifies the per-workspace face pipeline status endpoint returns
accurate counts and honors consent gating (403 when consent is off).
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_backfill_job import FaceBackfillJob
from api.db.models.face_detection import FaceDetection
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.file import File
from api.services import flags
from api.services.face import consent_service, crypto
from api.services.face.consent_text import CURRENT_CONSENT_VERSION

pytestmark = pytest.mark.asyncio(loop_scope="session")

_STATUS_URL = "/api/v1/face/status"


def _auth(tok: dict, *, with_csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    if with_csrf:
        h["X-CSRF-Token"] = tok["csrf_token"]
    return h


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


async def _seed_face_data(
    db, workspace_id: UUID, user_id: UUID, *, faces: int, processed: int
) -> None:
    """Minimal seed: create a source + files + photo_assets + face_detections.
    ``processed`` photos have face_processed_at set; ``faces`` of those
    also get one FaceDetection row apiece.
    """
    src = Source(
        workspace_id=workspace_id,
        name=f"status-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for i in range(processed):
        f = File(
            workspace_id=workspace_id,
            source_id=src.id,
            filename=f"p{i}.jpg",
            path=f"/tmp/p{i}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10,
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        has_face = i < faces
        pa = PhotoAsset(
            file_id=f.id,
            workspace_id=workspace_id,
            face_count=1 if has_face else 0,
            face_processed_at=now,
        )
        db.add(pa)
        await db.flush()
        if has_face:
            det = FaceDetection(
                workspace_id=workspace_id,
                photo_asset_id=pa.id,
                bbox_json={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                embedding_encrypted=b"ct",
                embedding_dim=512,
                detector_version="v1",
                recognizer_version="v1",
                detection_score=0.9,
                qdrant_point_id=uuid4(),
            )
            db.add(det)
    await db.flush()


class TestFaceStatusEndpoint:
    async def test_requires_consent(self, client, auth_tokens):
        resp = await client.get(_STATUS_URL, headers=_auth(auth_tokens))
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"

    async def test_returns_counts_when_consent_active(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        # Grant consent
        grant = await client.post(
            "/api/v1/settings/face-clustering/consent",
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers=_auth(auth_tokens, with_csrf=True),
            cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
        )
        assert grant.status_code == 200

        # Seed 5 processed photos, 3 with a detection row
        async with test_session_factory() as db:
            await _seed_face_data(
                db,
                auth_tokens["workspace_id"],
                auth_tokens["user_id"],
                faces=3,
                processed=5,
            )
            await db.commit()

        resp = await client.get(_STATUS_URL, headers=_auth(auth_tokens))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workspace_id"] == str(auth_tokens["workspace_id"])
        assert body["consent"]["accepted"] is True
        assert body["face_count"] == 3
        assert body["photos_with_faces"] == 3
        assert body["photos_without_faces"] == 2
        assert body["model"]["detector_version"]
        assert body["model"]["recognizer_version"]
        assert body["backfill"]["state"] == "none"

    async def test_backfill_state_reflected(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        await client.post(
            "/api/v1/settings/face-clustering/consent",
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers=_auth(auth_tokens, with_csrf=True),
            cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
        )
        async with test_session_factory() as db:
            job = FaceBackfillJob(
                workspace_id=auth_tokens["workspace_id"],
                total_photos=20,
                processed_photos=7,
                failed_photos=0,
                state="running",
            )
            db.add(job)
            await db.commit()

        resp = await client.get(_STATUS_URL, headers=_auth(auth_tokens))
        assert resp.status_code == 200
        body = resp.json()
        assert body["backfill"]["state"] == "running"
        assert body["backfill"]["progress"] == "7/20"
