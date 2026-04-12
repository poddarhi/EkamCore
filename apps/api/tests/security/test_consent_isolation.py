"""Security test: face consent isolation between workspaces (S11-002).

Golden Rule #1 requires workspace isolation on EVERY query. This test
exercises the specific case of biometric consent: workspace A's consent
must not enable the face pipeline for workspace B, even if they share a
user or have identical consent timestamps.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.face import consent_service


async def _make_workspace(db, owner_user_id, name: str):
    ws = Workspace(name=name, type="personal", owner_id=owner_user_id)
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner_user_id, role="admin"))
    await db.flush()
    return ws


@pytest.mark.asyncio
class TestConsentIsolation:
    async def test_grant_in_a_does_not_activate_b(
        self, test_session_factory, seed_user
    ):
        """Consent in workspace A must not make workspace B's pipeline active."""
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            ws_a = await _make_workspace(db, user_id, "A")
            ws_b = await _make_workspace(db, user_id, "B")
            await db.commit()
            ws_a_id = ws_a.id
            ws_b_id = ws_b.id

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws_a_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            active_a = await consent_service.is_consent_active(ws_a_id, db)
            active_b = await consent_service.is_consent_active(ws_b_id, db)

        assert active_a is True, "Workspace A should be active after grant"
        assert active_b is False, (
            "Workspace B must NOT be active — workspace isolation violated"
        )

    async def test_revoke_in_a_does_not_affect_b(
        self, test_session_factory, seed_user
    ):
        """Revoking consent in A must not revoke or mutate B's consent."""
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            ws_a = await _make_workspace(db, user_id, "A")
            ws_b = await _make_workspace(db, user_id, "B")
            await db.commit()
            ws_a_id = ws_a.id
            ws_b_id = ws_b.id

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws_a_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="test",
                db=db,
            )
            await consent_service.grant(
                workspace_id=ws_b_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        # Both active
        async with test_session_factory() as db:
            assert await consent_service.is_consent_active(ws_a_id, db) is True
            assert await consent_service.is_consent_active(ws_b_id, db) is True

        # Revoke A only
        async with test_session_factory() as db:
            await consent_service.revoke(
                workspace_id=ws_a_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            a_still_active = await consent_service.is_consent_active(ws_a_id, db)
            b_still_active = await consent_service.is_consent_active(ws_b_id, db)

        assert a_still_active is False, "Workspace A should be revoked"
        assert b_still_active is True, (
            "Workspace B must remain active — cross-workspace leakage detected"
        )

    async def test_unknown_workspace_has_no_consent(
        self, test_session_factory
    ):
        """Reading consent for a workspace that doesn't exist returns False
        (no crash, no false positive)."""
        unknown = uuid4()
        async with test_session_factory() as db:
            active = await consent_service.is_consent_active(unknown, db)
        assert active is False
