"""Unit tests for trusted_person_service (S12-004).

Drive the service directly against the dev DB. Each test seeds a
workspace + face_cluster (and optionally a contact) and asserts:

  - create_from_cluster → person row, cluster linked, audit row
  - confirm_candidate happy path
  - confirm_candidate with unknown contact_id → INVALID_CANDIDATE
  - reject_cluster → cluster_state='rejected', audit row
  - rename → display_name updated, audit row
  - delete → deleted_at set, cluster link preserved
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import and_, select

from api.db.models.audit_log import AuditLog
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.errors import NotFoundError, ValidationError
from api.services import flags
from api.services.face import crypto, trusted_person_service

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


async def _mk_cluster(
    db, workspace_id: UUID, *, candidates: list | None = None
) -> UUID:
    cluster = FaceCluster(
        workspace_id=workspace_id,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=5,
        cluster_state="unconfirmed",
        candidates_json=candidates,
    )
    db.add(cluster)
    await db.flush()
    return cluster.id


async def _mk_contact(
    db, workspace_id: UUID, uid: UUID, *, display_name: str
) -> UUID:
    src = Source(
        workspace_id=workspace_id,
        name=f"tp-src-{uuid4().hex[:6]}",
        type="contacts",
        registered_by=uid,
        status="active",
    )
    db.add(src)
    await db.flush()
    c = Contact(
        workspace_id=workspace_id,
        source_id=src.id,
        external_id=uuid4().hex,
        first_name=display_name.split()[0],
        last_name=display_name.split()[-1] if " " in display_name else None,
        display_name=display_name,
        emails_json=[{"address": "x@example.com"}],
        imported_at=datetime.now(timezone.utc),
    )
    db.add(c)
    await db.flush()
    return c.id


class TestTrustedPersonService:
    async def test_create_from_cluster_links_and_audits(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            cluster_id = await _mk_cluster(db, ws)
            await db.commit()

        async with test_session_factory() as db:
            person = await trusted_person_service.create_from_cluster(
                cluster_id=cluster_id,
                workspace_id=ws,
                user_id=uid,
                display_name="Alice Smith",
                db=db,
            )
            person_id = person.id
            await db.commit()

        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
            row = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == person_id)
                )
            ).scalar_one()
            audits = (
                (
                    await db.execute(
                        select(AuditLog).where(
                            and_(
                                AuditLog.workspace_id == ws,
                                AuditLog.action == "person_created_from_cluster",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert cluster.cluster_state == "confirmed"
        assert cluster.trusted_person_id == person_id
        assert row.display_name == "Alice Smith"
        assert row.trust_source == "manual"
        assert row.confirmed_by == uid
        assert row.confirmed_at is not None
        assert len(audits) == 1
        assert audits[0].metadata_json["cluster_id"] == str(cluster_id)

    async def test_confirm_candidate_happy_path(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            contact_id = await _mk_contact(db, ws, uid, display_name="Bob Jones")
            cluster_id = await _mk_cluster(
                db, ws,
                candidates=[
                    {
                        "contact_id": str(contact_id),
                        "score": 0.9,
                        "confidence": "high",
                        "signals": {"co_occurrence": 1.0},
                    }
                ],
            )
            await db.commit()

        async with test_session_factory() as db:
            person = await trusted_person_service.confirm_candidate(
                cluster_id=cluster_id,
                contact_id=contact_id,
                workspace_id=ws,
                user_id=uid,
                db=db,
            )
            await db.commit()

        assert person.canonical_contact_id == contact_id
        assert person.trust_source == "face_confirmed"
        assert person.display_name == "Bob Jones"

        async with test_session_factory() as db:
            audits = (
                (
                    await db.execute(
                        select(AuditLog).where(
                            and_(
                                AuditLog.workspace_id == ws,
                                AuditLog.action == "person_confirmed_from_candidate",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(audits) == 1

    async def test_confirm_candidate_with_unknown_contact_raises(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            # Cluster has Alice as the only cached candidate.
            alice_id = await _mk_contact(db, ws, uid, display_name="Alice A")
            cluster_id = await _mk_cluster(
                db, ws,
                candidates=[
                    {
                        "contact_id": str(alice_id),
                        "score": 0.6,
                        "confidence": "medium",
                        "signals": {},
                    }
                ],
            )
            # Stranger contact exists but isn't on the candidate list.
            stranger_id = await _mk_contact(
                db, ws, uid, display_name="Stranger Danger"
            )
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(ValidationError) as excinfo:
                await trusted_person_service.confirm_candidate(
                    cluster_id=cluster_id,
                    contact_id=stranger_id,
                    workspace_id=ws,
                    user_id=uid,
                    db=db,
                )
        assert excinfo.value.error_code == "INVALID_CANDIDATE"

    async def test_reject_cluster_sets_state_and_audits(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            cluster_id = await _mk_cluster(db, ws)
            await db.commit()

        async with test_session_factory() as db:
            await trusted_person_service.reject_cluster(
                cluster_id=cluster_id,
                workspace_id=ws,
                user_id=uid,
                reason="not actually a person",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
            audits = (
                (
                    await db.execute(
                        select(AuditLog).where(
                            and_(
                                AuditLog.workspace_id == ws,
                                AuditLog.action == "cluster_rejected",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert cluster.cluster_state == "rejected"
        assert cluster.trusted_person_id is None
        assert len(audits) == 1
        assert audits[0].metadata_json["reason"] == "not actually a person"

    async def test_rename_updates_display_name(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            cluster_id = await _mk_cluster(db, ws)
            person = await trusted_person_service.create_from_cluster(
                cluster_id=cluster_id,
                workspace_id=ws,
                user_id=uid,
                display_name="Old Name",
                db=db,
            )
            person_id = person.id
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
            row = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == person_id)
                )
            ).scalar_one()
        assert row.display_name == "New Name"

    async def test_delete_soft_deletes_and_preserves_cluster_link(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            cluster_id = await _mk_cluster(db, ws)
            person = await trusted_person_service.create_from_cluster(
                cluster_id=cluster_id,
                workspace_id=ws,
                user_id=uid,
                display_name="ToDelete",
                db=db,
            )
            person_id = person.id
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
            row = (
                await db.execute(
                    select(TrustedPerson).where(TrustedPerson.id == person_id)
                )
            ).scalar_one()
            cluster = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
        assert row.deleted_at is not None
        # Cluster link is preserved for historical tag resolution.
        assert cluster.trusted_person_id == person_id
        assert cluster.cluster_state == "confirmed"

        # And get_person now raises because the row is soft-deleted.
        async with test_session_factory() as db:
            with pytest.raises(NotFoundError):
                await trusted_person_service.get_person(
                    person_id=person_id, workspace_id=ws, db=db
                )
