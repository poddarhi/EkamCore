"""Integration tests for merge/split/undo endpoints (S12-006)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
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
from api.services.face import consent_service, crypto

pytestmark = pytest.mark.asyncio(loop_scope="session")

_BASE = "/api/v1/people"


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


async def _grant(factory, ws, uid):
    async with factory() as db:
        await consent_service.grant(
            workspace_id=ws, user_id=uid,
            ip="127.0.0.1", user_agent="pytest", db=db,
        )
        await db.commit()


async def _seed_two_persons(factory, ws) -> tuple[UUID, UUID, UUID]:
    """Return (keeper_id, other_id, other_cluster_id)."""
    async with factory() as db:
        keeper = TrustedPerson(
            workspace_id=ws, display_name="Keeper", trust_source="manual"
        )
        other = TrustedPerson(
            workspace_id=ws, display_name="Other", trust_source="manual"
        )
        db.add_all([keeper, other])
        await db.flush()
        cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=3,
            cluster_state="confirmed",
            trusted_person_id=other.id,
        )
        db.add(cluster)
        await db.commit()
        return keeper.id, other.id, cluster.id


async def _seed_person_with_faces(factory, ws, uid) -> tuple[UUID, UUID, list[UUID]]:
    async with factory() as db:
        src = Source(
            workspace_id=ws, name=f"op-{uuid4().hex[:6]}",
            type="photo_folder", registered_by=uid, status="active",
        )
        db.add(src)
        await db.flush()
        person = TrustedPerson(workspace_id=ws, display_name="Original", trust_source="manual")
        db.add(person)
        await db.flush()
        cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=6,
            cluster_state="confirmed",
            trusted_person_id=person.id,
        )
        db.add(cluster)
        await db.flush()
        fds: list[UUID] = []
        for i in range(6):
            f = File(
                workspace_id=ws, source_id=src.id,
                filename=f"op-{i}.jpg", path=f"/tmp/{uuid4().hex}.jpg",
                content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                size_bytes=10, mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=1)
            db.add(pa)
            await db.flush()
            vec = [0.0] * 512
            vec[i] = 1.0
            det = FaceDetection(
                workspace_id=ws, photo_asset_id=pa.id,
                bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
                embedding_encrypted=crypto.encrypt_embedding(vec),
                embedding_dim=512, detector_version="t", recognizer_version="t",
                detection_score=0.9, qdrant_point_id=uuid4(),
                cluster_id=cluster.id,
            )
            db.add(det)
            await db.flush()
            fds.append(det.id)
        await db.commit()
        return person.id, cluster.id, fds


def _h(t, *, csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {t['access_token']}"}
    if csrf:
        h["X-CSRF-Token"] = t["csrf_token"]
    return h


def _c(t) -> dict:
    return {"ekamcore_csrf": t["csrf_token"]}


class TestOperationsEndpoints:
    async def test_merge_endpoint_happy_path(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        keeper_id, other_id, _ = await _seed_two_persons(
            test_session_factory, ws
        )

        resp = await client.post(
            f"{_BASE}/merge",
            json={
                "person_ids": [str(keeper_id), str(other_id)],
                "keeper_id": str(keeper_id),
            },
            headers=_h(auth_tokens, csrf=True),
            cookies=_c(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == str(keeper_id)

    async def test_split_endpoint_happy_path(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        person_id, _, fds = await _seed_person_with_faces(
            test_session_factory, ws, uid
        )

        resp = await client.post(
            f"{_BASE}/{person_id}/split",
            json={
                "face_detection_ids": [str(fds[0]), str(fds[1])],
                "new_display_name": "Split Out",
            },
            headers=_h(auth_tokens, csrf=True),
            cookies=_c(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["display_name"] == "Split Out"
        assert body["id"] != str(person_id)

    async def test_undo_last_endpoint(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        keeper_id, other_id, _ = await _seed_two_persons(
            test_session_factory, ws
        )
        # Perform a merge first.
        resp = await client.post(
            f"{_BASE}/merge",
            json={
                "person_ids": [str(keeper_id), str(other_id)],
                "keeper_id": str(keeper_id),
            },
            headers=_h(auth_tokens, csrf=True),
            cookies=_c(auth_tokens),
        )
        assert resp.status_code == 200

        resp = await client.post(
            f"{_BASE}/operations/undo-last",
            headers=_h(auth_tokens, csrf=True),
            cookies=_c(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["operation_type"] == "merge"

        async with test_session_factory() as db:
            other = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == other_id)
                )
            ).scalar_one()
        assert other.deleted_at is None

    async def test_undo_specific_and_list(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant(test_session_factory, ws, uid)
        # Seed a person and rename via the real endpoint so an op is recorded.
        async with test_session_factory() as db:
            p = TrustedPerson(
                workspace_id=ws, display_name="Pre", trust_source="manual"
            )
            db.add(p)
            await db.commit()
            person_id = p.id

        resp = await client.patch(
            f"{_BASE}/{person_id}",
            json={"display_name": "Post"},
            headers=_h(auth_tokens, csrf=True),
            cookies=_c(auth_tokens),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"{_BASE}/operations", headers=_h(auth_tokens)
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert any(i["operation_type"] == "rename" for i in items)
        op_id = next(i["id"] for i in items if i["operation_type"] == "rename")

        resp = await client.post(
            f"{_BASE}/operations/{op_id}/undo",
            headers=_h(auth_tokens, csrf=True),
            cookies=_c(auth_tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["operation_id"] == op_id

        async with test_session_factory() as db:
            p = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == person_id)
                )
            ).scalar_one()
        assert p.display_name == "Pre"
