"""Unit tests for undo_service (S12-006)."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.person_operation import PersonOperation
from api.db.models.trusted_person import TrustedPerson
from api.errors import ConflictError
from api.services import flags
from api.services.face import (
    crypto,
    merge_service,
    split_service,
    trusted_person_service,
    undo_service,
)

# Reuse fixture helpers from the sibling unit tests.
from tests.unit.test_split_service import _seed_person_with_faces  # noqa: E402

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


async def _mk_person(db, ws, name="x") -> UUID:
    p = TrustedPerson(workspace_id=ws, display_name=name, trust_source="manual")
    db.add(p)
    await db.flush()
    return p.id


async def _mk_cluster(db, ws, person_id) -> UUID:
    c = FaceCluster(
        workspace_id=ws,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=3,
        cluster_state="confirmed",
        trusted_person_id=person_id,
    )
    db.add(c)
    await db.flush()
    return c.id


class TestUndo:
    async def test_undo_merge_restores_state(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            keeper = await _mk_person(db, ws, "Keeper")
            p2 = await _mk_person(db, ws, "P2")
            c2 = await _mk_cluster(db, ws, p2)
            await db.commit()

        async with test_session_factory() as db:
            await merge_service.merge_persons(
                person_ids=[keeper, p2],
                keeper_id=keeper,
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
            p2_row = (
                await db.execute(select(TrustedPerson).where(TrustedPerson.id == p2))
            ).scalar_one()
            cluster = (
                await db.execute(select(FaceCluster).where(FaceCluster.id == c2))
            ).scalar_one()
            keeper_row = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == keeper)
                )
            ).scalar_one()
        assert p2_row.deleted_at is None
        assert cluster.trusted_person_id == p2
        assert not (keeper_row.merged_from_ids or [])

    async def test_undo_split_restores_state(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id, cluster_id, fds = await _seed_person_with_faces(
                db, ws, uid, count=10
            )
            await db.commit()
        split_out = fds[:3]

        async with test_session_factory() as db:
            await split_service.split_person(
                person_id=person_id,
                face_detection_ids=split_out,
                new_display_name="Split Out",
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
            original_cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
            restored_fds = (
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
            all_persons = (
                (
                    await db.execute(
                        select(TrustedPerson).where(
                            TrustedPerson.workspace_id == ws
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert original_cluster.member_count == 10
        assert all(f.cluster_id == cluster_id for f in restored_fds)
        # The newly-minted split person was hard-deleted on undo.
        assert len(all_persons) == 1
        assert all_persons[0].id == person_id

    async def test_undo_rename_restores_old_name(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id = await _mk_person(db, ws, "Original")
            await db.commit()

        async with test_session_factory() as db:
            await trusted_person_service.rename(
                person_id=person_id,
                workspace_id=ws,
                user_id=uid,
                new_name="New Name",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await undo_service.undo_last_operation(
                workspace_id=ws, user_id=uid, db=db
            )
            await db.commit()

        async with test_session_factory() as db:
            p = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == person_id)
                )
            ).scalar_one()
        assert p.display_name == "Original"

    async def test_undo_delete_restores_person(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id = await _mk_person(db, ws, "ToDelete")
            await db.commit()

        async with test_session_factory() as db:
            await trusted_person_service.delete(
                person_id=person_id,
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
            p = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == person_id)
                )
            ).scalar_one()
        assert p.deleted_at is None

    async def test_double_undo_returns_409(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id = await _mk_person(db, ws, "Anybody")
            await db.commit()
        async with test_session_factory() as db:
            await trusted_person_service.rename(
                person_id=person_id,
                workspace_id=ws,
                user_id=uid,
                new_name="Changed",
                db=db,
            )
            await db.commit()
        async with test_session_factory() as db:
            result = await undo_service.undo_last_operation(
                workspace_id=ws, user_id=uid, db=db
            )
            op_id = result.operation_id
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(ConflictError) as excinfo:
                await undo_service.undo_specific_operation(
                    operation_id=op_id,
                    workspace_id=ws,
                    user_id=uid,
                    db=db,
                )
        assert excinfo.value.error_code == "OPERATION_ALREADY_UNDONE"
