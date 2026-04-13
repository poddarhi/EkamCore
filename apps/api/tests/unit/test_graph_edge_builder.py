"""Unit tests for graph_edge_builder (S12-007)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import and_, select

from api.db.models.calendar_event import CalendarEvent
from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.graph_edge import GraphEdge
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.services import flags
from api.services.face import crypto, graph_edge_builder

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


async def _seed_person_with_photos(
    db, ws, uid, *, photo_count: int, canonical_contact_id: UUID | None = None
) -> UUID:
    src = Source(
        workspace_id=ws, name=f"ge-{uuid4().hex[:6]}",
        type="photo_folder", registered_by=uid, status="active",
    )
    db.add(src)
    await db.flush()
    person = TrustedPerson(
        workspace_id=ws, display_name="P",
        trust_source="manual",
        canonical_contact_id=canonical_contact_id,
    )
    db.add(person)
    await db.flush()
    cluster = FaceCluster(
        workspace_id=ws,
        centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
        member_count=photo_count,
        cluster_state="confirmed",
        trusted_person_id=person.id,
    )
    db.add(cluster)
    await db.flush()
    for i in range(photo_count):
        f = File(
            workspace_id=ws, source_id=src.id,
            filename=f"ge-{i}.jpg",
            path=f"/tmp/{uuid4().hex}.jpg",
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=10, mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=1)
        db.add(pa)
        await db.flush()
        det = FaceDetection(
            workspace_id=ws, photo_asset_id=pa.id,
            bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
            embedding_encrypted=crypto.encrypt_embedding([0.0] * 512),
            embedding_dim=512, detector_version="t", recognizer_version="t",
            detection_score=0.9, qdrant_point_id=uuid4(),
            cluster_id=cluster.id,
        )
        db.add(det)
        await db.flush()
    return person.id


async def _count_person_photo_edges(db, ws, person_id) -> int:
    rows = (
        await db.execute(
            select(GraphEdge).where(
                and_(
                    GraphEdge.workspace_id == ws,
                    GraphEdge.from_type == "trusted_person",
                    GraphEdge.from_id == person_id,
                    GraphEdge.to_type == "photo_asset",
                    GraphEdge.edge_type == "appears_in",
                )
            )
        )
    ).scalars().all()
    return len(rows)


class TestGraphEdgeBuilder:
    async def test_photo_edges_happy_path(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id = await _seed_person_with_photos(
                db, ws, uid, photo_count=5
            )
            await db.commit()
        async with test_session_factory() as db:
            written = await graph_edge_builder.build_person_photo_edges(
                workspace_id=ws, db=db
            )
            await db.commit()
        assert written == 5
        async with test_session_factory() as db:
            assert await _count_person_photo_edges(db, ws, person_id) == 5

    async def test_photo_edges_are_idempotent(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            person_id = await _seed_person_with_photos(
                db, ws, uid, photo_count=3
            )
            await db.commit()
        async with test_session_factory() as db:
            await graph_edge_builder.build_person_photo_edges(
                workspace_id=ws, db=db
            )
            await db.commit()
        async with test_session_factory() as db:
            await graph_edge_builder.build_person_photo_edges(
                workspace_id=ws, db=db
            )
            await db.commit()
        async with test_session_factory() as db:
            assert await _count_person_photo_edges(db, ws, person_id) == 3

    async def test_event_edges_match_by_email(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            src = Source(
                workspace_id=ws, name="ge-ev",
                type="contacts", registered_by=uid, status="active",
            )
            db.add(src)
            await db.flush()
            contact = Contact(
                workspace_id=ws, source_id=src.id, external_id=uuid4().hex,
                first_name="Alice", last_name="Smith", display_name="Alice Smith",
                emails_json=[{"address": "alice@example.com"}],
                imported_at=datetime.now(timezone.utc),
            )
            db.add(contact)
            await db.flush()
            person_id = await _seed_person_with_photos(
                db, ws, uid, photo_count=1,
                canonical_contact_id=contact.id,
            )
            base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
            for i in range(3):
                db.add(
                    CalendarEvent(
                        workspace_id=ws, source_id=src.id,
                        external_id=uuid4().hex, title="Meet",
                        start_at=base + timedelta(days=i),
                        end_at=base + timedelta(days=i, hours=1),
                        participants_json=[
                            {"email": "alice@example.com", "name": "Alice Smith"}
                        ],
                    )
                )
            # An event Alice did NOT attend.
            db.add(
                CalendarEvent(
                    workspace_id=ws, source_id=src.id,
                    external_id=uuid4().hex, title="Skip",
                    start_at=base + timedelta(days=10),
                    end_at=base + timedelta(days=10, hours=1),
                    participants_json=[
                        {"email": "bob@example.com", "name": "Bob"}
                    ],
                )
            )
            await db.commit()

        async with test_session_factory() as db:
            written = await graph_edge_builder.build_person_event_edges(
                workspace_id=ws, db=db
            )
            await db.commit()
        assert written == 3

        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    select(GraphEdge).where(
                        and_(
                            GraphEdge.workspace_id == ws,
                            GraphEdge.from_type == "trusted_person",
                            GraphEdge.from_id == person_id,
                            GraphEdge.to_type == "calendar_event",
                            GraphEdge.edge_type == "attended",
                        )
                    )
                )
            ).scalars().all()
        assert len(rows) == 3

    async def test_event_edges_skipped_when_no_canonical_contact(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            await _seed_person_with_photos(db, ws, uid, photo_count=1)
            # Calendar event exists but the person has no contact link.
            src = (
                await db.execute(select(Source).where(Source.workspace_id == ws))
            ).scalars().first()
            db.add(
                CalendarEvent(
                    workspace_id=ws, source_id=src.id,
                    external_id=uuid4().hex, title="X",
                    start_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
                    participants_json=[{"email": "x@y.com"}],
                )
            )
            await db.commit()
        async with test_session_factory() as db:
            written = await graph_edge_builder.build_person_event_edges(
                workspace_id=ws, db=db
            )
            await db.commit()
        assert written == 0

    async def test_file_edges_placeholder_returns_zero(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        uid = seed_user["user_id"]
        async with test_session_factory() as db:
            await _seed_person_with_photos(db, ws, uid, photo_count=1)
            await db.commit()
        async with test_session_factory() as db:
            written = await graph_edge_builder.build_person_file_edges(
                workspace_id=ws, db=db
            )
            await db.commit()
        assert written == 0
