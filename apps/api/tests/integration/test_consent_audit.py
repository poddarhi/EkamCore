"""Integration test: face consent lifecycle emits correct audit log rows (S11-002).

Validates the end-to-end audit trail:
  grant → one `face_consent_granted` row with version, IP, UA, metadata
  revoke → one `face_consent_revoked` row with original grant correlation
  Both rows queryable by workspace_id and appear in chronological order.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from api.db.models.audit_log import AuditLog
from api.services.face import consent_service
from api.services.face.consent_text import CURRENT_CONSENT_VERSION


@pytest.mark.asyncio
class TestConsentAuditTrail:
    async def test_grant_writes_audit_row_with_all_fields(
        self, test_session_factory, seed_user
    ):
        workspace_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="203.0.113.10",
                user_agent="Mozilla/5.0 EkamCore-web",
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
        assert row.action == "face_consent_granted"
        assert row.object_type == "face_consent"
        assert row.user_id == user_id
        assert row.workspace_id == workspace_id
        assert str(row.source_ip) == "203.0.113.10"
        assert row.user_agent == "Mozilla/5.0 EkamCore-web"
        assert row.metadata_json is not None
        assert row.metadata_json["consent_version"] == CURRENT_CONSENT_VERSION
        assert row.metadata_json["consent_text_version"] == CURRENT_CONSENT_VERSION
        assert row.created_at is not None

    async def test_revoke_writes_second_audit_row_with_correlation(
        self, test_session_factory, seed_user
    ):
        workspace_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="203.0.113.10",
                user_agent="grant-agent",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await consent_service.revoke(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="203.0.113.11",
                user_agent="revoke-agent",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.object_type == "face_consent",
                )
                .order_by(AuditLog.id)
            )
            rows = result.scalars().all()

        # S11-003: revoke now also emits a face_data_hard_deleted row between
        # grant and revoke (from the atomic hard-delete step).
        actions = [r.action for r in rows]
        assert actions == [
            "face_consent_granted",
            "face_data_hard_deleted",
            "face_consent_revoked",
        ]

        grant_row = rows[0]
        revoke_row = rows[2]
        assert grant_row.action == "face_consent_granted"
        assert revoke_row.action == "face_consent_revoked"

        # Revoke row correlates back to the original grant
        assert revoke_row.metadata_json is not None
        assert "original_granted_at" in revoke_row.metadata_json
        assert "original_granted_by_user_id" in revoke_row.metadata_json
        assert revoke_row.metadata_json["original_granted_by_user_id"] == str(user_id)
        assert revoke_row.user_agent == "revoke-agent"
        assert str(revoke_row.source_ip) == "203.0.113.11"

    async def test_audit_rows_queryable_by_workspace(
        self, test_session_factory, seed_user
    ):
        """The workspace_id column on object_audit_log is indexed and
        the row must be findable by a simple workspace filter."""
        workspace_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="203.0.113.10",
                user_agent="test",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            result = await db.execute(
                select(AuditLog).where(AuditLog.workspace_id == workspace_id)
            )
            rows = result.scalars().all()

        assert any(r.action == "face_consent_granted" for r in rows)
