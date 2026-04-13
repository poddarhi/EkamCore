"""Unit tests for split_service (S12-006)."""

from __future__ import annotations

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
from api.errors import ValidationError
from api.services import flags
from api.services.face import crypto, split_service

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


async def _seed_person_with_faces(
    db, ws, uid, *, count: int
) -> tuple[UUID, UUID, list[UUID]]:
    src = Source(
        workspace_id=ws, name=f"sp-{uuid4().hex[:6]}", type="photo_folder",
        registered_by=uid, status="active",
    )
    db.add(src)
    await db.flush()
    person = TrustedPerson(workspace_id=ws, display_name="Original", trust_source="manual")
    db.add(person)
    await db.flush()
    cluster = FaceCluster(
        workspace_id=ws,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=count,
        cluster_state="confirmed",
        trusted_person_id=person.id,
    )
    db.add(cluster)
    await db.flush()
    fd_ids: list[UUID] = []
    for i in range(count):
        f = File(
            workspace_id=ws, source_id=src.id,
            filename=f"sp-{i}.jpg",
            path=f"/tmp/{uuid4().hex}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10, mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=1)
        db.add(pa)
        await db.flush()
        vec = [0.0] * 512
        vec[i % 512] = 1.0
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
        fd_ids.append(det.id)
    return person.id, cluster.id, fd_ids


class TestSplitService:
    async def test_split_five_of_twenty(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id, cluster_id, fds = await _seed_person_with_faces(
                db, ws, uid, count=20
            )
            await db.commit()

        split_out = fds[:5]
        async with test_session_factory() as db:
            original, new_person = await split_service.split_person(
                person_id=person_id,
                face_detection_ids=split_out,
                new_display_name="Split Out",
                workspace_id=ws,
                user_id=uid,
                db=db,
            )
            original_id = original.id
            new_id = new_person.id
            await db.commit()

        async with test_session_factory() as db:
            original_cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
            new_cluster = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.trusted_person_id == new_id
                    )
                )
            ).scalar_one()
            split_out_fds = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.id.in_(split_out)
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert original_cluster.member_count == 15
        assert new_cluster.member_count == 5
        assert all(f.cluster_id == new_cluster.id for f in split_out_fds)
        assert original_id == person_id
        assert new_id != person_id

    async def test_split_with_unknown_face_raises(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id, _, _ = await _seed_person_with_faces(
                db, ws, uid, count=5
            )
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(ValidationError) as excinfo:
                await split_service.split_person(
                    person_id=person_id,
                    face_detection_ids=[uuid4()],
                    new_display_name="x",
                    workspace_id=ws,
                    user_id=uid,
                    db=db,
                )
        assert excinfo.value.error_code == "SPLIT_FACES_NOT_FOUND"
