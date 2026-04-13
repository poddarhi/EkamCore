"""Workspace isolation for graph_edge_builder (S12-007).

Two workspaces each have a confirmed person, its cluster, and
photos. Rebuilding the edges for workspace A must produce only
workspace-A edges — none of workspace B's photos can be reachable
from A's person, and vice versa.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import and_, select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.graph_edge import GraphEdge
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.auth import hash_password
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


async def _mk_ws(factory, label: str) -> tuple[UUID, UUID]:
    async with factory() as db:
        u = User(
            email=f"gi-{label}-{uuid4().hex[:6]}@ekamcore.dev",
            display_name=f"GI {label}",
            password_hash=hash_password("testpassword123"),
            role="standard",
            is_active=True,
        )
        db.add(u)
        await db.flush()
        ws = Workspace(name=f"GI {label}", type="personal", owner_id=u.id)
        db.add(ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role="admin"))
        await db.commit()
        return ws.id, u.id


async def _seed_person(factory, ws, uid) -> tuple[UUID, list[UUID]]:
    async with factory() as db:
        src = Source(
            workspace_id=ws, name=f"gi-{uuid4().hex[:6]}",
            type="photo_folder", registered_by=uid, status="active",
        )
        db.add(src)
        await db.flush()
        person = TrustedPerson(
            workspace_id=ws, display_name="P", trust_source="manual"
        )
        db.add(person)
        await db.flush()
        cluster = FaceCluster(
            workspace_id=ws,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=3,
            cluster_state="confirmed",
            trusted_person_id=person.id,
        )
        db.add(cluster)
        await db.flush()
        photo_ids: list[UUID] = []
        for i in range(3):
            f = File(
                workspace_id=ws, source_id=src.id,
                filename=f"gi-{i}.jpg", path=f"/tmp/{uuid4().hex}.jpg",
                content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                size_bytes=10, mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=1)
            db.add(pa)
            await db.flush()
            photo_ids.append(pa.id)
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
        await db.commit()
        return person.id, photo_ids


class TestGraphEdgeIsolation:
    async def test_workspace_a_edges_never_reference_workspace_b_photos(
        self, test_session_factory, face_env
    ):
        ws_a, uid_a = await _mk_ws(test_session_factory, "A")
        ws_b, uid_b = await _mk_ws(test_session_factory, "B")
        person_a, photos_a = await _seed_person(test_session_factory, ws_a, uid_a)
        person_b, photos_b = await _seed_person(test_session_factory, ws_b, uid_b)

        async with test_session_factory() as db:
            await graph_edge_builder.build_person_photo_edges(
                workspace_id=ws_a, db=db
            )
            await db.commit()

        async with test_session_factory() as db:
            a_edges = (
                (
                    await db.execute(
                        select(GraphEdge).where(
                            and_(
                                GraphEdge.workspace_id == ws_a,
                                GraphEdge.from_type == "trusted_person",
                                GraphEdge.from_id == person_a,
                                GraphEdge.to_type == "photo_asset",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(a_edges) == 3
        reached = {e.to_id for e in a_edges}
        assert reached == set(photos_a)
        assert not (reached & set(photos_b))

        # Nothing was written for workspace B because we only
        # rebuilt workspace A.
        async with test_session_factory() as db:
            b_edges = (
                (
                    await db.execute(
                        select(GraphEdge).where(
                            and_(
                                GraphEdge.workspace_id == ws_b,
                                GraphEdge.from_type == "trusted_person",
                                GraphEdge.to_type == "photo_asset",
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert b_edges == []
