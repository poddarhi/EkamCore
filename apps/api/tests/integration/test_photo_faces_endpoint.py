"""Integration tests for the photo lightbox endpoints (S13-008)."""

from __future__ import annotations

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

_PHOTOS_URL = "/api/v1/photos"

# 1x1 red JPEG — tiny fixture written to disk so /full can read it.
_JPEG_BYTES = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043000806060706050806070707"
    "09090a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c283728"
    "2c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d1832211c21"
    "3232323232323232323232323232323232323232323232323232323232323232323232323"
    "232323232323232323232323232ffc00011080001000103012200021101031101ffc4001"
    "f0000010501010101010100000000000000000102030405060708090a0bffc400b510000"
    "2010303020403050504040000017d01020300041105122131410613516107227114328191"
    "a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434"
    "4454647484950535455565758595a636465666768696a737475767778797a83848586878"
    "88990929394959697989999a2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8"
    "c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f0100"
    "03010101010101010101010000000000000102030405060708090a0bffc400b5110002010"
    "20404030407050404000102770001021103210412314105516106134171227181083291a1"
    "b1c117324252f0156272d10a162434e125f11718191a262728292a35363738393a4344454"
    "647484950535455565758595a636465666768696a737475767778797a82838485868788898"
    "a92939495969798999a2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2"
    "d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311"
    "003f00fbfa28a2803ffd9"
)


@pytest.fixture
def face_env():
    key = Fernet.generate_key().decode()
    with (
        patch.object(flags, "_ENABLED_FLAGS", {"face_clustering_enabled", "photos_enabled"}),
        patch.object(flags.settings, "FACE_EMBED_KEY", key),
    ):
        crypto._reset_cache()
        try:
            yield key
        finally:
            crypto._reset_cache()


def _auth_headers(tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _grant_consent(factory, ws, uid):
    async with factory() as db:
        await consent_service.grant(
            workspace_id=ws,
            user_id=uid,
            ip="127.0.0.1",
            user_agent="pytest",
            db=db,
        )
        await db.commit()


async def _seed_photo_with_faces(
    factory, ws, uid, *, jpeg_path, with_person: bool
) -> tuple[UUID, UUID, UUID]:
    async with factory() as db:
        src = Source(
            workspace_id=ws,
            name=f"lb-{uuid4().hex[:6]}",
            type="photo_folder",
            registered_by=uid,
            status="active",
        )
        db.add(src)
        await db.flush()

        f = File(
            workspace_id=ws,
            source_id=src.id,
            filename="photo.jpg",
            path=str(jpeg_path),
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=len(_JPEG_BYTES),
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()

        photo = PhotoAsset(
            file_id=f.id,
            workspace_id=ws,
            taken_at=datetime.now(timezone.utc),
            face_count=2,
        )
        db.add(photo)
        await db.flush()

        person_id = None
        bound_cluster_id = None
        if with_person:
            person = TrustedPerson(
                workspace_id=ws,
                display_name="Alice",
                trust_source="manual",
            )
            db.add(person)
            await db.flush()
            person_id = person.id
            bound_cluster = FaceCluster(
                workspace_id=ws,
                centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
                member_count=1,
                cluster_state="confirmed",
                trusted_person_id=person.id,
            )
            db.add(bound_cluster)
            await db.flush()
            bound_cluster_id = bound_cluster.id

        unbound_cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=1,
            cluster_state="unconfirmed",
            trusted_person_id=None,
        )
        db.add(unbound_cluster)
        await db.flush()

        # Known face (bound to person) + unknown face (floating cluster)
        if with_person and bound_cluster_id is not None:
            db.add(
                FaceDetection(
                    workspace_id=ws,
                    photo_asset_id=photo.id,
                    bbox_json={"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
                    embedding_encrypted=crypto.encrypt_embedding([0.0] * 512),
                    embedding_dim=512,
                    detector_version="t",
                    recognizer_version="t",
                    detection_score=0.95,
                    qdrant_point_id=uuid4(),
                    cluster_id=bound_cluster_id,
                )
            )
        db.add(
            FaceDetection(
                workspace_id=ws,
                photo_asset_id=photo.id,
                bbox_json={"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2},
                embedding_encrypted=crypto.encrypt_embedding([0.0] * 512),
                embedding_dim=512,
                detector_version="t",
                recognizer_version="t",
                detection_score=0.9,
                qdrant_point_id=uuid4(),
                cluster_id=unbound_cluster.id,
            )
        )

        await db.commit()
        return photo.id, person_id, unbound_cluster.id


class TestPhotoFacesEndpoint:
    async def test_returns_faces_with_person_linkage(
        self, client, auth_tokens, test_session_factory, face_env, tmp_path
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        jpeg_path = tmp_path / "photo.jpg"
        jpeg_path.write_bytes(_JPEG_BYTES)

        photo_id, person_id, _ = await _seed_photo_with_faces(
            test_session_factory,
            ws,
            uid,
            jpeg_path=jpeg_path,
            with_person=True,
        )

        resp = await client.get(
            f"{_PHOTOS_URL}/{photo_id}/faces",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 2
        known = next(
            (i for i in body["items"] if i["trusted_person_id"] is not None),
            None,
        )
        unknown = next(
            (i for i in body["items"] if i["trusted_person_id"] is None),
            None,
        )
        assert known is not None and unknown is not None
        assert known["trusted_person_id"] == str(person_id)
        assert known["trusted_person_display_name"] == "Alice"
        assert known["trusted_person_avatar_url"].endswith(
            f"/people/{person_id}/avatar"
        )
        assert unknown["trusted_person_display_name"] is None
        assert unknown["trusted_person_avatar_url"] is None
        # bbox round-trip
        for item in body["items"]:
            assert "x" in item["bbox"] and "w" in item["bbox"]

    async def test_returns_empty_list_when_no_faces(
        self, client, auth_tokens, test_session_factory, face_env, tmp_path
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        jpeg_path = tmp_path / "noface.jpg"
        jpeg_path.write_bytes(_JPEG_BYTES)

        async with test_session_factory() as db:
            src = Source(
                workspace_id=ws,
                name=f"lb-{uuid4().hex[:6]}",
                type="photo_folder",
                registered_by=uid,
                status="active",
            )
            db.add(src)
            await db.flush()
            f = File(
                workspace_id=ws,
                source_id=src.id,
                filename="p.jpg",
                path=str(jpeg_path),
                content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                size_bytes=10,
                mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            photo = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=0)
            db.add(photo)
            await db.commit()
            photo_id = photo.id

        resp = await client.get(
            f"{_PHOTOS_URL}/{photo_id}/faces",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    async def test_faces_404_on_unknown_id(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        resp = await client.get(
            f"{_PHOTOS_URL}/{uuid4()}/faces",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "PHOTO_NOT_FOUND"

    async def test_faces_requires_consent(
        self, client, auth_tokens, face_env
    ):
        # No consent granted.
        resp = await client.get(
            f"{_PHOTOS_URL}/{uuid4()}/faces",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"

    async def test_full_endpoint_returns_jpeg(
        self, client, auth_tokens, test_session_factory, face_env, tmp_path
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        jpeg_path = tmp_path / "full.jpg"
        jpeg_path.write_bytes(_JPEG_BYTES)

        photo_id, _, _ = await _seed_photo_with_faces(
            test_session_factory,
            ws,
            uid,
            jpeg_path=jpeg_path,
            with_person=False,
        )

        resp = await client.get(
            f"{_PHOTOS_URL}/{photo_id}/full",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "image/jpeg"
        assert resp.content.startswith(b"\xff\xd8\xff")

    async def test_full_404_on_unknown_id(
        self, client, auth_tokens, face_env
    ):
        resp = await client.get(
            f"{_PHOTOS_URL}/{uuid4()}/full",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "PHOTO_NOT_FOUND"
