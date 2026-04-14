"""Integration tests for GET /api/v1/people/{id}/avatar (S13-002).

Seeds a person with one cluster containing one face_detection whose
bbox_json points at a tiny synthetic PNG written to a tmp directory.
The endpoint should return JPEG bytes with a Cache-Control header.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.services import flags
from api.services.face import consent_service, crypto

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


def _tiny_png(tmp_path, name: str = "face.jpg") -> str:
    from PIL import Image

    img = Image.new("RGB", (200, 200), color=(128, 64, 200))
    out = tmp_path / name
    img.save(out, format="JPEG", quality=80)
    return str(out)


async def _grant(factory, ws, uid):
    async with factory() as db:
        await consent_service.grant(
            workspace_id=ws, user_id=uid,
            ip="127.0.0.1", user_agent="pytest", db=db,
        )
        await db.commit()


async def _seed_person_with_face(factory, ws, uid, image_path: str) -> UUID:
    async with factory() as db:
        src = Source(
            workspace_id=ws, name=f"av-{uuid4().hex[:6]}",
            type="photo_folder", registered_by=uid, status="active",
        )
        db.add(src)
        await db.flush()
        person = TrustedPerson(
            workspace_id=ws, display_name="Alice", trust_source="manual"
        )
        db.add(person)
        await db.flush()
        cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=1,
            cluster_state="confirmed",
            trusted_person_id=person.id,
        )
        db.add(cluster)
        await db.flush()
        f = File(
            workspace_id=ws, source_id=src.id,
            filename="face.jpg", path=image_path,
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10, mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=1)
        db.add(pa)
        await db.flush()
        det = FaceDetection(
            workspace_id=ws, photo_asset_id=pa.id,
            bbox_json={"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5},
            embedding_encrypted=crypto.encrypt_embedding([0.0] * 512),
            embedding_dim=512, detector_version="t", recognizer_version="t",
            detection_score=0.95, qdrant_point_id=uuid4(),
            cluster_id=cluster.id,
        )
        db.add(det)
        await db.commit()
        return person.id


def _h(tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


class TestPersonAvatar:
    async def test_returns_jpeg_for_person_with_face(
        self, client, auth_tokens, test_session_factory, face_env, tmp_path
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        image_path = _tiny_png(tmp_path)
        person_id = await _seed_person_with_face(
            test_session_factory, ws, uid, image_path
        )

        resp = await client.get(
            f"/api/v1/people/{person_id}/avatar",
            headers=_h(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "image/jpeg"
        assert "max-age=3600" in resp.headers.get("cache-control", "")
        assert len(resp.content) > 0
        # Pillow should round-trip the bytes back to a valid image.
        from PIL import Image
        img = Image.open(io.BytesIO(resp.content))
        assert img.format == "JPEG"

    async def test_returns_404_for_person_without_face(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        async with test_session_factory() as db:
            person = TrustedPerson(
                workspace_id=ws, display_name="Faceless",
                trust_source="manual",
            )
            db.add(person)
            await db.commit()
            person_id = person.id

        resp = await client.get(
            f"/api/v1/people/{person_id}/avatar",
            headers=_h(auth_tokens),
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error_code"] == "PERSON_AVATAR_UNAVAILABLE"

    async def test_search_param_filters_by_display_name(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        async with test_session_factory() as db:
            for name in ("Alice Alpha", "Bob Bravo", "Alice Avocado"):
                db.add(
                    TrustedPerson(
                        workspace_id=ws, display_name=name,
                        trust_source="manual",
                    )
                )
            await db.commit()

        resp = await client.get(
            "/api/v1/people?search=alice",
            headers=_h(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        names = {p["display_name"] for p in resp.json()["items"]}
        assert "Alice Alpha" in names
        assert "Alice Avocado" in names
        assert "Bob Bravo" not in names
