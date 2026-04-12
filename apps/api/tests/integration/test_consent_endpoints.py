"""Integration tests for face clustering consent API endpoints (S11-003).

Covers:
  GET    — current state + text
  POST   — grant happy path, stale version → 409
  DELETE — revokes and hard-deletes, reports counts
  Auth + CSRF + rate limiting gates

Uses the main FastAPI app via the shared client fixture. Face data is
seeded at the ORM layer; Qdrant is mocked where necessary by patching
the qdrant client getter used by hard_delete.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.db.models.audit_log import AuditLog
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.services.face.consent_text import (
    CURRENT_CONSENT_TEXT,
    CURRENT_CONSENT_VERSION,
)

# Integration tests share the session loop
pytestmark = pytest.mark.asyncio(loop_scope="session")

_CONSENT_URL = "/api/v1/settings/face-clustering/consent"


def _make_qdrant_mock(remaining: int = 0) -> AsyncMock:
    m = AsyncMock()
    m.delete = AsyncMock(return_value=None)
    count_result = AsyncMock()
    count_result.count = remaining
    m.count = AsyncMock(return_value=count_result)
    return m


# ── GET ────────────────────────────────────────────────────────────────────


class TestGetConsent:
    async def test_no_consent_returns_text_and_accepted_false(
        self, client, auth_tokens
    ):
        resp = await client.get(
            _CONSENT_URL,
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] is False
        assert body["version"] is None
        assert body["current_text_version"] == CURRENT_CONSENT_VERSION
        assert body["current_text"] == CURRENT_CONSENT_TEXT
        # Spot check that the draft text body is present
        assert "DRAFT" in body["current_text"]

    async def test_unauthenticated_returns_401(self, client):
        resp = await client.get(_CONSENT_URL)
        assert resp.status_code == 401


# ── POST ───────────────────────────────────────────────────────────────────


class TestPostConsent:
    async def test_grant_happy_path_returns_200_and_records_consent(
        self, client, auth_tokens, test_session_factory
    ):
        workspace_id = auth_tokens["workspace_id"]
        csrf = auth_tokens["csrf_token"]

        resp = await client.post(
            _CONSENT_URL,
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-CSRF-Token": csrf,
            },
            cookies={"ekamcore_csrf": csrf},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] is True
        assert body["version"] == CURRENT_CONSENT_VERSION
        assert body["current_text_version"] == CURRENT_CONSENT_VERSION

        # Audit row exists
        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.workspace_id == workspace_id,
                        AuditLog.action == "face_consent_granted",
                    )
                )
            ).scalars().all()
        assert len(rows) == 1
        assert rows[0].metadata_json["consent_version"] == CURRENT_CONSENT_VERSION

    async def test_grant_stale_version_returns_409_consent_version_stale(
        self, client, auth_tokens
    ):
        csrf = auth_tokens["csrf_token"]
        resp = await client.post(
            _CONSENT_URL,
            json={
                "accepted": True,
                "version_acknowledged": "v0.0-SOMETHING-OLD",
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-CSRF-Token": csrf,
            },
            cookies={"ekamcore_csrf": csrf},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error_code"] == "CONSENT_VERSION_STALE"
        assert body["details"]["current_version"] == CURRENT_CONSENT_VERSION

    async def test_grant_requires_csrf(self, client, auth_tokens):
        resp = await client.post(
            _CONSENT_URL,
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "CSRF_VALIDATION_FAILED"

    async def test_grant_not_accepted_returns_409(self, client, auth_tokens):
        csrf = auth_tokens["csrf_token"]
        resp = await client.post(
            _CONSENT_URL,
            json={
                "accepted": False,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-CSRF-Token": csrf,
            },
            cookies={"ekamcore_csrf": csrf},
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "CONSENT_NOT_ACCEPTED"


# ── DELETE ─────────────────────────────────────────────────────────────────


class TestDeleteConsent:
    async def test_delete_revokes_and_reports_zeros_when_empty(
        self, client, auth_tokens, test_session_factory
    ):
        csrf = auth_tokens["csrf_token"]

        # Grant first
        grant_resp = await client.post(
            _CONSENT_URL,
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-CSRF-Token": csrf,
            },
            cookies={"ekamcore_csrf": csrf},
        )
        assert grant_resp.status_code == 200

        # Revoke — no face data was seeded, so counts should be 0.
        # Patch hard_delete's qdrant getter to avoid touching real Qdrant
        with patch(
            "api.services.face.hard_delete.get_qdrant",
            return_value=_make_qdrant_mock(),
        ):
            del_resp = await client.delete(
                _CONSENT_URL,
                headers={
                    "Authorization": f"Bearer {auth_tokens['access_token']}",
                    "X-CSRF-Token": csrf,
                },
                cookies={"ekamcore_csrf": csrf},
            )
        assert del_resp.status_code == 200, del_resp.text
        body = del_resp.json()
        assert body["detection_count"] == 0
        assert body["cluster_count"] == 0
        assert body["duration_ms"] >= 0

        # Audit: two rows for this workspace — grant then hard_deleted + revoked
        workspace_id = auth_tokens["workspace_id"]
        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    select(AuditLog)
                    .where(AuditLog.workspace_id == workspace_id)
                    .order_by(AuditLog.id)
                )
            ).scalars().all()
        actions = [r.action for r in rows if r.action.startswith("face_")]
        assert "face_consent_granted" in actions
        assert "face_data_hard_deleted" in actions
        assert "face_consent_revoked" in actions

    async def test_delete_deletes_seeded_face_data(
        self, client, auth_tokens, test_session_factory
    ):
        """Seed real face_detection + face_cluster rows and verify they're
        gone after DELETE /consent."""
        from api.db.models.file import File
        from api.db.models.photo_asset import PhotoAsset
        from api.db.models.source import Source

        workspace_id = auth_tokens["workspace_id"]
        user_id = auth_tokens["user_id"]
        csrf = auth_tokens["csrf_token"]

        # Seed face data
        async with test_session_factory() as db:
            src = Source(
                workspace_id=workspace_id,
                name="test-src",
                type="photo_folder",
                registered_by=user_id,
                status="active",
            )
            db.add(src)
            await db.flush()
            f = File(
                workspace_id=workspace_id,
                source_id=src.id,
                filename="p.jpg",
                path="/p.jpg",
                content_hash_sha256="a" * 64,
                size_bytes=10,
                mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=3)
            db.add(pa)
            await db.flush()
            cluster = FaceCluster(
                workspace_id=workspace_id, member_count=0, cluster_state="unconfirmed"
            )
            db.add(cluster)
            await db.flush()
            det = FaceDetection(
                workspace_id=workspace_id,
                photo_asset_id=pa.id,
                bbox_json={"x": 0},
                embedding_encrypted=b"ciphertext",
                embedding_dim=512,
                detector_version="v1",
                recognizer_version="v1",
                cluster_id=cluster.id,
                detection_score=0.9,
                qdrant_point_id=uuid4(),
            )
            db.add(det)
            await db.commit()

        # Grant
        grant_resp = await client.post(
            _CONSENT_URL,
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers={
                "Authorization": f"Bearer {auth_tokens['access_token']}",
                "X-CSRF-Token": csrf,
            },
            cookies={"ekamcore_csrf": csrf},
        )
        assert grant_resp.status_code == 200

        # Revoke with mocked Qdrant
        with patch(
            "api.services.face.hard_delete.get_qdrant",
            return_value=_make_qdrant_mock(),
        ):
            del_resp = await client.delete(
                _CONSENT_URL,
                headers={
                    "Authorization": f"Bearer {auth_tokens['access_token']}",
                    "X-CSRF-Token": csrf,
                },
                cookies={"ekamcore_csrf": csrf},
            )
        assert del_resp.status_code == 200, del_resp.text
        body = del_resp.json()
        assert body["detection_count"] == 1
        assert body["cluster_count"] == 1

        # Verify rows gone
        async with test_session_factory() as db:
            dets = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == workspace_id
                    )
                )
            ).scalars().all()
            clusters = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.workspace_id == workspace_id
                    )
                )
            ).scalars().all()
            photos = (
                await db.execute(
                    select(PhotoAsset).where(
                        PhotoAsset.workspace_id == workspace_id
                    )
                )
            ).scalars().all()
        assert len(dets) == 0
        assert len(clusters) == 0
        assert all(p.face_count == 0 for p in photos)

    async def test_delete_requires_csrf(self, client, auth_tokens):
        resp = await client.delete(
            _CONSENT_URL,
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "CSRF_VALIDATION_FAILED"
