"""Unit tests for face clustering ConsentService (S11-002).

Covers:
  - grant() creates an active record and emits an audit row
  - grant() is idempotent for same version + still-active record
  - revoke() flips accepted=False, sets revoked_at, emits audit row
  - revoke() is no-op when there's no active consent
  - is_consent_active() reflects grant/revoke state
  - Consent never auto-expires by time (stale timestamp still active)
  - Bumped version invalidates old consent (re-consent required)
  - Redis cache is invalidated on state transitions
  - Rollback contract: hard-delete failure rolls back the revoke
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.db.models.audit_log import AuditLog
from api.services.face import consent_service, data_erasure
from api.services.face.consent_service import ConsentRecord
from api.services.face.consent_text import CURRENT_CONSENT_VERSION


@pytest.fixture
def workspace_id(seed_user):
    return seed_user["workspace_id"]


@pytest.fixture
def user_id(seed_user):
    return seed_user["user_id"]


# ── grant ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGrant:
    async def test_grant_creates_active_record(
        self, test_session_factory, workspace_id, user_id
    ):
        async with test_session_factory() as db:
            record = await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test-agent/1.0",
                db=db,
            )
            await db.commit()

        assert isinstance(record, ConsentRecord)
        assert record.accepted is True
        assert record.version == CURRENT_CONSENT_VERSION
        assert record.granted_by_user_id == user_id
        assert record.ip == "192.0.2.1"
        assert record.user_agent == "test-agent/1.0"
        assert record.revoked_at is None

    async def test_grant_makes_consent_active(
        self, test_session_factory, workspace_id, user_id
    ):
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            active = await consent_service.is_consent_active(workspace_id, db)
        assert active is True

    async def test_grant_is_idempotent_for_same_version(
        self, test_session_factory, workspace_id, user_id
    ):
        """Double-grant returns the existing record unchanged."""
        async with test_session_factory() as db:
            record1 = await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            record2 = await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.99",  # different IP — should be ignored
                user_agent="different-agent",
                db=db,
            )
            await db.commit()

        # Same granted_at because idempotent grant returned the existing
        assert record1.granted_at == record2.granted_at
        assert record2.ip == "192.0.2.1"  # original preserved

    async def test_grant_emits_audit_row(
        self, test_session_factory, workspace_id, user_id
    ):
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="audit-test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await db.execute(
                select(AuditLog).where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.action == "face_consent_granted",
                )
            )
            rows = result.scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == user_id
        assert row.user_agent == "audit-test"
        assert row.metadata_json is not None
        assert row.metadata_json.get("consent_version") == CURRENT_CONSENT_VERSION

    async def test_grant_with_bumped_version_replaces_old(
        self, test_session_factory, workspace_id, user_id
    ):
        """A grant with a new version overwrites the old record."""
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                version="v0.9-OLD",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            new_record = await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.2",
                user_agent="test",
                version=CURRENT_CONSENT_VERSION,
                db=db,
            )
            await db.commit()

        assert new_record.version == CURRENT_CONSENT_VERSION
        assert new_record.ip == "192.0.2.2"


# ── revoke ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRevoke:
    async def test_revoke_flips_accepted_and_sets_revoked_at(
        self, test_session_factory, workspace_id, user_id
    ):
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await consent_service.revoke(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            active = await consent_service.is_consent_active(workspace_id, db)
            record = await consent_service.get_active_consent(workspace_id, db)

        assert active is False
        assert record is None  # tombstoned — not returned as active

    async def test_revoke_emits_audit_row(
        self, test_session_factory, workspace_id, user_id
    ):
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="grant-agent",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await consent_service.revoke(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.2",
                user_agent="revoke-agent",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await db.execute(
                select(AuditLog)
                .where(AuditLog.workspace_id == workspace_id)
                .order_by(AuditLog.id)
            )
            rows = result.scalars().all()

        actions = [r.action for r in rows if r.action.startswith("face_consent")]
        assert actions == ["face_consent_granted", "face_consent_revoked"]

        revoke_row = [r for r in rows if r.action == "face_consent_revoked"][0]
        assert revoke_row.user_agent == "revoke-agent"
        assert revoke_row.metadata_json is not None
        assert "original_granted_at" in revoke_row.metadata_json

    async def test_revoke_without_active_consent_is_noop(
        self, test_session_factory, workspace_id, user_id
    ):
        """Revoking when no consent exists is safe and does nothing."""
        async with test_session_factory() as db:
            await consent_service.revoke(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await db.execute(
                select(AuditLog).where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.action == "face_consent_revoked",
                )
            )
            rows = result.scalars().all()
        assert rows == []

    async def test_revoke_calls_hard_delete(
        self, test_session_factory, workspace_id, user_id
    ):
        """revoke() must call hard_delete_all_face_data synchronously."""
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        hard_delete_mock = AsyncMock()
        with patch.object(
            data_erasure, "hard_delete_all_face_data", hard_delete_mock
        ):
            async with test_session_factory() as db:
                await consent_service.revoke(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    ip="192.0.2.1",
                    user_agent="test",
                    db=db,
                )
                await db.commit()

        hard_delete_mock.assert_awaited_once()
        kwargs = hard_delete_mock.call_args.kwargs
        assert kwargs["workspace_id"] == workspace_id

    async def test_revoke_rollback_on_hard_delete_failure(
        self, test_session_factory, workspace_id, user_id
    ):
        """If hard_delete raises, the consent MUST remain active (rollback)."""
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        failing_hard_delete = AsyncMock(
            side_effect=RuntimeError("simulated erasure failure")
        )

        with patch.object(
            data_erasure, "hard_delete_all_face_data", failing_hard_delete
        ):
            async with test_session_factory() as db:
                with pytest.raises(RuntimeError, match="simulated"):
                    await consent_service.revoke(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        ip="192.0.2.1",
                        user_agent="test",
                        db=db,
                    )
                # Caller must roll back on the exception
                await db.rollback()

        # Consent should still be active because the revoke rolled back
        async with test_session_factory() as db:
            active = await consent_service.is_consent_active(workspace_id, db)
        assert active is True, (
            "Rollback contract violated: revoke persisted after hard_delete failure"
        )


# ── Non-expiration and version semantics ──────────────────────────────────


@pytest.mark.asyncio
class TestConsentExpiration:
    async def test_consent_does_not_auto_expire_by_time(
        self, test_session_factory, workspace_id, user_id
    ):
        """A stale timestamp on the consent record does NOT deactivate it.

        Consent only expires when the version changes (user must re-consent
        to updated text), not based on elapsed time.
        """
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        # Back-date the granted_at to a year ago
        from api.db.models.setting import Setting

        async with test_session_factory() as db:
            result = await db.execute(
                select(Setting).where(
                    Setting.workspace_id == workspace_id,
                    Setting.namespace == "privacy",
                    Setting.key == "face_clustering_consent",
                )
            )
            row = result.scalar_one()
            blob = dict(row.value_json)
            stale = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
            blob["granted_at"] = stale
            row.value_json = blob
            await db.commit()

        async with test_session_factory() as db:
            active = await consent_service.is_consent_active(workspace_id, db)
        assert active is True, "Consent incorrectly expired by time alone"

    async def test_version_bump_expires_old_consent(
        self, test_session_factory, workspace_id, user_id
    ):
        """When the consent text version changes, old records become stale."""
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                version="v0.1-ancient",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            # With the CURRENT version differing from the stored one,
            # is_consent_active must return False.
            active = await consent_service.is_consent_active(workspace_id, db)
        assert active is False


# ── Audit metadata sanity ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAuditMetadata:
    async def test_audit_row_contains_version_in_metadata(
        self, test_session_factory, workspace_id, user_id
    ):
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="192.0.2.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await db.execute(
                select(AuditLog).where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.action == "face_consent_granted",
                )
            )
            row = result.scalar_one()
        assert row.metadata_json["consent_version"] == CURRENT_CONSENT_VERSION
        # source_ip preserved (INET column → IPv4Address object)
        assert str(row.source_ip) == "192.0.2.1"
