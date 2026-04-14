"""Integration tests for the Person detail endpoints (S13-003).

Covers the six new GETs (photos/files/events/reminders/faces/face
thumbnail) and the POST remove-face mutation. Reuses the consent +
seed helpers from ``test_people_endpoints.py`` to keep fixtures DRY.

Files and reminders deliberately return empty lists today — the
underlying linkage tables (paperless correspondent bridge,
reminder→person tagging) have not landed. The tests pin the
empty-list contract so a future bridge story does not silently
break the response shape.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.graph_edge import GraphEdge
from api.db.models.person_operation import PersonOperation
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.services import flags
from api.services.face import consent_service, crypto

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PEOPLE_URL = "/api/v1/people"


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


def _auth_headers(tokens, *, with_csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    if with_csrf:
        h["X-CSRF-Token"] = tokens["csrf_token"]
    return h


def _csrf_cookie(tokens) -> dict:
    return {"ekamcore_csrf": tokens["csrf_token"]}


async def _grant_consent(factory, workspace_id, user_id):
    async with factory() as db:
        await consent_service.grant(
            workspace_id=workspace_id,
            user_id=user_id,
            ip="127.0.0.1",
            user_agent="pytest",
            db=db,
        )
        await db.commit()


async def _seed_person_with_photos_and_faces(
    factory, workspace_id, user_id, *, photo_count: int = 3
):
    """Seed a TrustedPerson with N photos, each owning one face_detection
    that is part of a single FaceCluster bound to the person, plus the
    matching ``appears_in`` graph_edges. Returns (person_id, [photo_ids],
    [face_detection_ids])."""
    async with factory() as db:
        src = Source(
            workspace_id=workspace_id,
            name=f"pd-{uuid4().hex[:6]}",
            type="photo_folder",
            registered_by=user_id,
            status="active",
        )
        db.add(src)
        await db.flush()

        person = TrustedPerson(
            workspace_id=workspace_id,
            display_name="Detail Subject",
            trust_source="manual",
        )
        db.add(person)
        await db.flush()

        cluster = FaceCluster(
            workspace_id=workspace_id,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=photo_count,
            cluster_state="confirmed",
            trusted_person_id=person.id,
        )
        db.add(cluster)
        await db.flush()

        photo_ids: list = []
        face_ids: list = []
        for i in range(photo_count):
            f = File(
                workspace_id=workspace_id,
                source_id=src.id,
                filename=f"detail-{i}.jpg",
                path=f"/tmp/{uuid4().hex}.jpg",
                content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                size_bytes=100,
                mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            pa = PhotoAsset(
                file_id=f.id,
                workspace_id=workspace_id,
                taken_at=datetime.now(timezone.utc),
                face_count=1,
            )
            db.add(pa)
            await db.flush()
            vec = [0.0] * 512
            vec[i % 512] = 1.0
            det = FaceDetection(
                workspace_id=workspace_id,
                photo_asset_id=pa.id,
                bbox_json={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                embedding_encrypted=crypto.encrypt_embedding(vec),
                embedding_dim=512,
                detector_version="t",
                recognizer_version="t",
                detection_score=0.9 - i * 0.05,
                qdrant_point_id=uuid4(),
                cluster_id=cluster.id,
            )
            db.add(det)
            await db.flush()

            db.add(
                GraphEdge(
                    workspace_id=workspace_id,
                    from_type="trusted_person",
                    from_id=person.id,
                    to_type="photo_asset",
                    to_id=pa.id,
                    edge_type="appears_in",
                    evidence_json={
                        "cluster_ids": [str(cluster.id)],
                        "face_count": 1,
                    },
                    strength=0.5,
                )
            )

            photo_ids.append(pa.id)
            face_ids.append(det.id)
        await db.commit()
        return person.id, photo_ids, face_ids


class TestPersonDetailEndpoints:
    async def test_list_person_photos_returns_seeded_photos(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        person_id, photo_ids, _ = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=3
        )

        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}/photos",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == 3
        ids = {item["id"] for item in body["items"]}
        assert ids == {str(p) for p in photo_ids}
        for item in body["items"]:
            assert item["thumbnail_url"].startswith("/api/v1/photos/")
            assert item["face_count"] == 1

    async def test_list_person_photos_pagination(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        person_id, _, _ = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=4
        )

        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}/photos?limit=2",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

        resp2 = await client.get(
            f"{_PEOPLE_URL}/{person_id}/photos?limit=2&cursor={body['next_cursor']}",
            headers=_auth_headers(auth_tokens),
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["items"]) == 2
        first_ids = {i["id"] for i in body["items"]}
        second_ids = {i["id"] for i in body2["items"]}
        assert first_ids.isdisjoint(second_ids)

    async def test_files_endpoint_returns_empty_deferred(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        person_id, _, _ = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=1
        )

        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}/files",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "next_cursor": None}

    async def test_events_endpoint_returns_empty_when_no_edges(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        person_id, _, _ = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=1
        )

        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}/events",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_reminders_endpoint_returns_empty_deferred(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        person_id, _, _ = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=1
        )

        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}/reminders",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "next_cursor": None}

    async def test_faces_endpoint_returns_thumbnail_urls(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        person_id, _, face_ids = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=2
        )

        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}/faces",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        returned = {item["face_detection_id"] for item in body["items"]}
        assert returned == {str(fid) for fid in face_ids}
        for item in body["items"]:
            assert item["thumbnail_url"] == (
                f"/api/v1/people/{person_id}/faces/"
                f"{item['face_detection_id']}/thumbnail"
            )

    async def test_remove_face_detaches_and_logs_operation(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        person_id, _, face_ids = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=3
        )

        target = face_ids[0]
        resp = await client.post(
            f"{_PEOPLE_URL}/{person_id}/remove-face",
            json={"face_detection_id": str(target)},
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 204, resp.text

        async with test_session_factory() as db:
            face = (
                await db.execute(
                    select(FaceDetection).where(FaceDetection.id == target)
                )
            ).scalar_one()
            original_cluster = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.trusted_person_id == person_id
                    )
                )
            ).scalar_one()
            op = (
                await db.execute(
                    select(PersonOperation).where(
                        PersonOperation.workspace_id == ws,
                        PersonOperation.operation_type == "detach_face",
                    )
                )
            ).scalar_one()

        assert face.cluster_id != original_cluster.id
        assert op.forward_payload["face_detection_id"] == str(target)

    async def test_remove_face_rejects_face_from_other_person(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        _, _, fds_a = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=2
        )
        person_b, _, _ = await _seed_person_with_photos_and_faces(
            test_session_factory, ws, uid, photo_count=2
        )

        resp = await client.post(
            f"{_PEOPLE_URL}/{person_b}/remove-face",
            json={"face_detection_id": str(fds_a[0])},
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "FACE_NOT_IN_PERSON"

    async def test_detail_endpoints_require_consent(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        # Without consent, every detail endpoint must 403.
        person_id = uuid4()
        for path in ("photos", "files", "events", "reminders", "faces"):
            resp = await client.get(
                f"{_PEOPLE_URL}/{person_id}/{path}",
                headers=_auth_headers(auth_tokens),
            )
            assert resp.status_code == 403, path
            assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"

    async def test_detail_endpoints_require_workspace_match(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        # Reference an unknown person id — _ensure_person should 404.
        unknown = uuid4()
        resp = await client.get(
            f"{_PEOPLE_URL}/{unknown}/photos",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 404
