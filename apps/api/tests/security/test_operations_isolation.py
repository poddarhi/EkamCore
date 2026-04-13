"""Cross-workspace isolation for S12-006 merge/undo endpoints."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from api.db.models.trusted_person import TrustedPerson
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.auth import hash_password
from api.services.face import (
    consent_service,
    crypto,
    merge_service,
    trusted_person_service,
    undo_service,
)
from api.errors import NotFoundError

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


async def _mk_ws(factory, label: str) -> tuple[UUID, UUID]:
    async with factory() as db:
        u = User(
            email=f"ops-{label}-{uuid4().hex[:6]}@ekamcore.dev",
            display_name=f"Ops {label}",
            password_hash=hash_password("testpassword123"),
            role="standard",
            is_active=True,
        )
        db.add(u)
        await db.flush()
        ws = Workspace(name=f"Ops {label}", type="personal", owner_id=u.id)
        db.add(ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role="admin"))
        await consent_service.grant(
            workspace_id=ws.id, user_id=u.id,
            ip="127.0.0.1", user_agent="pytest", db=db,
        )
        await db.commit()
        return ws.id, u.id


async def _mk_person(factory, ws) -> UUID:
    async with factory() as db:
        p = TrustedPerson(workspace_id=ws, display_name="X", trust_source="manual")
        db.add(p)
        await db.commit()
        return p.id


class TestOperationsIsolation:
    async def test_cannot_merge_across_workspaces(
        self, test_session_factory, face_env
    ):
        ws_a, uid_a = await _mk_ws(test_session_factory, "A")
        ws_b, _ = await _mk_ws(test_session_factory, "B")
        person_a = await _mk_person(test_session_factory, ws_a)
        person_b = await _mk_person(test_session_factory, ws_b)

        async with test_session_factory() as db:
            with pytest.raises(NotFoundError):
                await merge_service.merge_persons(
                    person_ids=[person_a, person_b],
                    keeper_id=person_a,
                    workspace_id=ws_a,
                    user_id=uid_a,
                    db=db,
                )

    async def test_cannot_undo_foreign_operation(
        self, test_session_factory, face_env
    ):
        ws_a, uid_a = await _mk_ws(test_session_factory, "A")
        ws_b, uid_b = await _mk_ws(test_session_factory, "B")
        person_b = await _mk_person(test_session_factory, ws_b)

        # B renames → op recorded under ws_b.
        async with test_session_factory() as db:
            await trusted_person_service.rename(
                person_id=person_b,
                workspace_id=ws_b,
                user_id=uid_b,
                new_name="B new",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(NotFoundError):
                await undo_service.undo_last_operation(
                    workspace_id=ws_a, user_id=uid_a, db=db
                )
