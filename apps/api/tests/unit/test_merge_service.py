"""Unit tests for merge_service (S12-006)."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_cluster import FaceCluster
from api.db.models.person_operation import PersonOperation
from api.db.models.trusted_person import TrustedPerson
from api.errors import ValidationError
from api.services import flags
from api.services.face import crypto, merge_service

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


class TestMergeService:
    async def test_merge_three_into_keeper(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            keeper_id = await _mk_person(db, ws, "Keeper")
            p2 = await _mk_person(db, ws, "P2")
            p3 = await _mk_person(db, ws, "P3")
            c2 = await _mk_cluster(db, ws, p2)
            c3 = await _mk_cluster(db, ws, p3)
            await db.commit()

        async with test_session_factory() as db:
            keeper = await merge_service.merge_persons(
                person_ids=[keeper_id, p2, p3],
                keeper_id=keeper_id,
                workspace_id=ws,
                user_id=uid,
                db=db,
            )
            await db.commit()
            assert set(keeper.merged_from_ids or []) == {str(p2), str(p3)}

        async with test_session_factory() as db:
            p2_row = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == p2)
                )
            ).scalar_one()
            p3_row = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == p3)
                )
            ).scalar_one()
            c2_row = (
                await db.execute(select(FaceCluster).where(FaceCluster.id == c2))
            ).scalar_one()
            c3_row = (
                await db.execute(select(FaceCluster).where(FaceCluster.id == c3))
            ).scalar_one()
            ops = (
                (
                    await db.execute(
                        select(PersonOperation).where(
                            PersonOperation.workspace_id == ws
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert p2_row.deleted_at is not None
        assert p3_row.deleted_at is not None
        assert c2_row.trusted_person_id == keeper_id
        assert c3_row.trusted_person_id == keeper_id
        assert len(ops) == 1
        assert ops[0].operation_type == "merge"
        assert len(ops[0].inverse_payload["restored_persons"]) == 2

    async def test_merge_with_keeper_not_in_list_raises(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            p1 = await _mk_person(db, ws, "P1")
            p2 = await _mk_person(db, ws, "P2")
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(ValidationError) as excinfo:
                await merge_service.merge_persons(
                    person_ids=[p1, p2],
                    keeper_id=uuid4(),
                    workspace_id=ws,
                    user_id=uid,
                    db=db,
                )
        assert excinfo.value.error_code == "INVALID_MERGE_KEEPER"
