"""Integration test for /api/v1/internal/graph/rebuild (S12-007)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

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
from api.services.face import crypto

pytestmark = pytest.mark.asyncio(loop_scope="session")

_URL = "/api/v1/internal/graph/rebuild"


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


async def _full_seed(factory, ws, uid):
    async with factory() as db:
        src = Source(
            workspace_id=ws, name=f"gr-{uuid4().hex[:6]}",
            type="photo_folder", registered_by=uid, status="active",
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
        person = TrustedPerson(
            workspace_id=ws, display_name="Alice Smith",
            trust_source="manual",
            canonical_contact_id=contact.id,
        )
        db.add(person)
        await db.flush()
        cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=4,
            cluster_state="confirmed",
            trusted_person_id=person.id,
        )
        db.add(cluster)
        await db.flush()
        for i in range(4):
            f = File(
                workspace_id=ws, source_id=src.id,
                filename=f"gr-{i}.jpg", path=f"/tmp/{uuid4().hex}.jpg",
                content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                size_bytes=10, mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=1)
            db.add(pa)
            await db.flush()
            db.add(
                FaceDetection(
                    workspace_id=ws, photo_asset_id=pa.id,
                    bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
                    embedding_encrypted=crypto.encrypt_embedding([0.0] * 512),
                    embedding_dim=512, detector_version="t",
                    recognizer_version="t", detection_score=0.9,
                    qdrant_point_id=uuid4(),
                    cluster_id=cluster.id,
                )
            )
        base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(2):
            db.add(
                CalendarEvent(
                    workspace_id=ws, source_id=src.id,
                    external_id=uuid4().hex, title="Meet",
                    start_at=base + timedelta(days=i),
                    end_at=base + timedelta(days=i, hours=1),
                    participants_json=[{"email": "alice@example.com"}],
                )
            )
        await db.commit()
        return person.id


class TestGraphRebuildEndpoint:
    async def test_rebuild_all_returns_expected_counts(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        person_id = await _full_seed(test_session_factory, ws, uid)

        resp = await client.post(
            _URL,
            json={"workspace_id": str(ws), "scope": "all"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["photo_edges"] == 4
        assert body["event_edges"] == 2
        assert body["file_edges"] == 0

        async with test_session_factory() as db:
            total_person_edges = (
                await db.execute(
                    select(GraphEdge).where(
                        and_(
                            GraphEdge.workspace_id == ws,
                            GraphEdge.from_type == "trusted_person",
                            GraphEdge.from_id == person_id,
                        )
                    )
                )
            ).scalars().all()
        assert len(total_person_edges) == 6
