"""Security test: hard_delete strict workspace isolation (S11-003).

Verifies that revoking consent in workspace A hard-deletes ONLY A's
face data. B's face_detections, face_clusters, and photo_asset.face_count
must remain untouched. This is the counterpart to the cross-workspace
consent isolation test in S11-002.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services.face.hard_delete import delete_all_face_data


async def _make_workspace(db, owner_user_id: UUID, name: str) -> Workspace:
    ws = Workspace(name=name, type="personal", owner_id=owner_user_id)
    db.add(ws)
    await db.flush()
    db.add(
        WorkspaceMember(workspace_id=ws.id, user_id=owner_user_id, role="admin")
    )
    await db.flush()
    return ws


async def _seed_face_data(
    db,
    workspace_id: UUID,
    *,
    registered_by: UUID,
    name_prefix: str,
    n: int = 3,
) -> tuple[list[FaceDetection], list[FaceCluster]]:
    src = Source(
        workspace_id=workspace_id,
        name=f"{name_prefix}-src",
        type="photo_folder",
        registered_by=registered_by,
        status="active",
    )
    db.add(src)
    await db.flush()

    clusters = []
    for i in range(n):
        c = FaceCluster(
            workspace_id=workspace_id, member_count=0, cluster_state="unconfirmed"
        )
        db.add(c)
        clusters.append(c)
    await db.flush()

    detections = []
    for i in range(n):
        f = File(
            workspace_id=workspace_id,
            source_id=src.id,
            filename=f"{name_prefix}-{i}.jpg",
            path=f"/{name_prefix}/{i}.jpg",
            content_hash_sha256=f"{name_prefix}{i:062x}"[:64],
            size_bytes=100,
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=2)
        db.add(pa)
        await db.flush()
        det = FaceDetection(
            workspace_id=workspace_id,
            photo_asset_id=pa.id,
            bbox_json={"x": i},
            embedding_encrypted=b"ct",
            embedding_dim=512,
            detector_version="v1",
            recognizer_version="v1",
            cluster_id=clusters[i].id,
            detection_score=0.9,
            qdrant_point_id=uuid4(),
        )
        db.add(det)
        detections.append(det)
    await db.flush()
    return detections, clusters


def _qdrant_mock() -> AsyncMock:
    m = AsyncMock()
    m.delete = AsyncMock(return_value=None)
    cr = AsyncMock()
    cr.count = 0
    m.count = AsyncMock(return_value=cr)
    return m


@pytest.mark.asyncio
class TestHardDeleteIsolation:
    async def test_delete_workspace_a_leaves_workspace_b_intact(
        self, test_session_factory, seed_user
    ):
        user_id = seed_user["user_id"]

        # Seed two workspaces with face data
        async with test_session_factory() as db:
            ws_a = await _make_workspace(db, user_id, "A")
            ws_b = await _make_workspace(db, user_id, "B")
            await db.commit()
            ws_a_id = ws_a.id
            ws_b_id = ws_b.id

        async with test_session_factory() as db:
            await _seed_face_data(
                db, ws_a_id, registered_by=user_id, name_prefix="a", n=3
            )
            await _seed_face_data(
                db, ws_b_id, registered_by=user_id, name_prefix="b", n=5
            )
            await db.commit()

        # Delete workspace A only
        qdrant_mock = _qdrant_mock()
        async with test_session_factory() as db:
            report = await delete_all_face_data(
                workspace_id=ws_a_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        assert report.detection_count == 3
        assert report.cluster_count == 3

        # Workspace A is empty
        async with test_session_factory() as db:
            a_dets = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == ws_a_id
                    )
                )
            ).scalars().all()
            a_clusters = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.workspace_id == ws_a_id)
                )
            ).scalars().all()
            a_photos = (
                await db.execute(
                    select(PhotoAsset).where(PhotoAsset.workspace_id == ws_a_id)
                )
            ).scalars().all()

        assert len(a_dets) == 0
        assert len(a_clusters) == 0
        assert all(p.face_count == 0 for p in a_photos)

        # Workspace B is untouched
        async with test_session_factory() as db:
            b_dets = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == ws_b_id
                    )
                )
            ).scalars().all()
            b_clusters = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.workspace_id == ws_b_id)
                )
            ).scalars().all()
            b_photos = (
                await db.execute(
                    select(PhotoAsset).where(PhotoAsset.workspace_id == ws_b_id)
                )
            ).scalars().all()

        assert len(b_dets) == 5, "Workspace B detections were affected — isolation broken"
        assert len(b_clusters) == 5, "Workspace B clusters were affected — isolation broken"
        assert all(p.face_count == 2 for p in b_photos), (
            "Workspace B face_count was zeroed — isolation broken"
        )

    async def test_qdrant_delete_filter_uses_workspace_a_only(
        self, test_session_factory, seed_user
    ):
        """The Qdrant delete filter must carry workspace A's ID and nothing else."""
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            ws_a = await _make_workspace(db, user_id, "A")
            await db.commit()
            ws_a_id = ws_a.id

        async with test_session_factory() as db:
            await _seed_face_data(
                db, ws_a_id, registered_by=user_id, name_prefix="a", n=1
            )
            await db.commit()

        qdrant_mock = _qdrant_mock()
        async with test_session_factory() as db:
            await delete_all_face_data(
                workspace_id=ws_a_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        delete_call = qdrant_mock.delete.call_args
        selector = delete_call.kwargs["points_selector"]
        # Assert the filter has exactly one workspace_id condition equal to ws_a_id
        must_clauses = selector.filter.must
        workspace_conditions = [
            c for c in must_clauses if getattr(c, "key", None) == "workspace_id"
        ]
        assert len(workspace_conditions) == 1
        assert workspace_conditions[0].match.value == str(ws_a_id)
