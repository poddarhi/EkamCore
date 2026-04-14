"""Unit tests for detach_face_service (S13-003)."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.person_operation import PersonOperation
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.errors import NotFoundError, ValidationError
from api.services import flags
from api.services.face import crypto, detach_face_service, undo_service

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
        workspace_id=ws,
        name=f"df-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=uid,
        status="active",
    )
    db.add(src)
    await db.flush()
    person = TrustedPerson(
        workspace_id=ws, display_name="Detach Subject", trust_source="manual"
    )
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
            workspace_id=ws,
            source_id=src.id,
            filename=f"df-{i}.jpg",
            path=f"/tmp/{uuid4().hex}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10,
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=1)
        db.add(pa)
        await db.flush()
        vec = [0.0] * 512
        vec[i % 512] = 1.0
        det = FaceDetection(
            workspace_id=ws,
            photo_asset_id=pa.id,
            bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
            embedding_encrypted=crypto.encrypt_embedding(vec),
            embedding_dim=512,
            detector_version="t",
            recognizer_version="t",
            detection_score=0.9,
            qdrant_point_id=uuid4(),
            cluster_id=cluster.id,
        )
        db.add(det)
        await db.flush()
        fd_ids.append(det.id)
    return person.id, cluster.id, fd_ids


class TestDetachFaceService:
    async def test_detach_moves_face_to_unconfirmed_cluster(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id, original_cluster_id, fds = await _seed_person_with_faces(
                db, ws, uid, count=4
            )
            await db.commit()

        target = fds[0]
        async with test_session_factory() as db:
            new_cluster_id = await detach_face_service.detach_face(
                person_id=person_id,
                face_detection_id=target,
                workspace_id=ws,
                user_id=uid,
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            face = (
                await db.execute(
                    select(FaceDetection).where(FaceDetection.id == target)
                )
            ).scalar_one()
            new_cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == new_cluster_id)
                )
            ).scalar_one()
            original = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.id == original_cluster_id
                    )
                )
            ).scalar_one()
            op_row = (
                await db.execute(
                    select(PersonOperation).where(
                        PersonOperation.workspace_id == ws,
                        PersonOperation.operation_type == "detach_face",
                    )
                )
            ).scalar_one()

        assert face.cluster_id == new_cluster_id
        assert new_cluster.cluster_state == "unconfirmed"
        assert new_cluster.trusted_person_id is None
        assert new_cluster.member_count == 1
        assert original.member_count == 3
        assert op_row.inverse_payload["original_cluster_id"] == str(
            original_cluster_id
        )

    async def test_detach_unknown_face_raises_not_found(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id, _, _ = await _seed_person_with_faces(
                db, ws, uid, count=2
            )
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(NotFoundError) as excinfo:
                await detach_face_service.detach_face(
                    person_id=person_id,
                    face_detection_id=uuid4(),
                    workspace_id=ws,
                    user_id=uid,
                    db=db,
                )
        assert excinfo.value.error_code == "FACE_NOT_FOUND"

    async def test_detach_face_not_in_person_raises_validation(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            _, _, fds_a = await _seed_person_with_faces(db, ws, uid, count=2)
            person_b, _, _ = await _seed_person_with_faces(
                db, ws, uid, count=2
            )
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(ValidationError) as excinfo:
                await detach_face_service.detach_face(
                    person_id=person_b,
                    face_detection_id=fds_a[0],
                    workspace_id=ws,
                    user_id=uid,
                    db=db,
                )
        assert excinfo.value.error_code == "FACE_NOT_IN_PERSON"

    async def test_detach_then_undo_restores_state(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id, original_cluster_id, fds = await _seed_person_with_faces(
                db, ws, uid, count=3
            )
            await db.commit()

        target = fds[0]
        async with test_session_factory() as db:
            new_cluster_id = await detach_face_service.detach_face(
                person_id=person_id,
                face_detection_id=target,
                workspace_id=ws,
                user_id=uid,
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await undo_service.undo_last_operation(
                workspace_id=ws, user_id=uid, db=db
            )
            await db.commit()

        async with test_session_factory() as db:
            face = (
                await db.execute(
                    select(FaceDetection).where(FaceDetection.id == target)
                )
            ).scalar_one()
            original = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.id == original_cluster_id
                    )
                )
            ).scalar_one()
            new_cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == new_cluster_id)
                )
            ).scalar_one()

        assert face.cluster_id == original_cluster_id
        assert original.member_count == 3
        assert new_cluster.deleted_at is not None
