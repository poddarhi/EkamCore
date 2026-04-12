"""Unit tests for face data hard-delete (S11-003).

Covers:
  - Seed N face_detections + M clusters → delete → all gone
  - Audit row written with correct counts and duration
  - photo_assets.face_count zeroed
  - Qdrant delete-by-filter called with correct workspace filter
  - Qdrant verify called
  - DeleteReport shape

Qdrant is mocked to keep this a PG-level unit test. Integration with a
real Qdrant instance is exercised in tests/integration/test_consent_endpoints.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from api.db.models.audit_log import AuditLog
from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.photo_asset import PhotoAsset
from api.errors import ServiceUnavailableError
from api.services.face.hard_delete import delete_all_face_data


@pytest.fixture
def workspace_id(seed_user) -> UUID:
    return seed_user["workspace_id"]


@pytest.fixture
def seed_user_id(seed_user) -> UUID:
    return seed_user["user_id"]


def _make_qdrant_mock(remaining_after_delete: int = 0) -> AsyncMock:
    """Mock AsyncQdrantClient with delete+count configured."""
    mock = AsyncMock()
    mock.delete = AsyncMock(return_value=None)
    count_result = AsyncMock()
    count_result.count = remaining_after_delete
    mock.count = AsyncMock(return_value=count_result)
    return mock


async def _seed_face_data(
    db,
    workspace_id: UUID,
    *,
    registered_by: UUID,
    n_detections: int,
    n_clusters: int,
) -> tuple[list[PhotoAsset], list[FaceCluster], list[FaceDetection]]:
    """Seed N photo_assets, M clusters, and detections distributed across them.

    Returns (photos, clusters, detections). Photos are needed because
    face_detections FKs to photo_assets.
    """
    # Photo assets (need files first)
    from api.db.models.file import File
    from api.db.models.source import Source

    source = Source(
        workspace_id=workspace_id,
        name="hd-test",
        type="photo_folder",
        registered_by=registered_by,
        status="active",
    )
    db.add(source)
    await db.flush()

    photos = []
    for i in range(max(n_detections, 1)):
        file = File(
            workspace_id=workspace_id,
            source_id=source.id,
            filename=f"photo_{i}.jpg",
            path=f"/test/photo_{i}.jpg",
            content_hash_sha256=f"{i:064x}",
            size_bytes=1024,
            mime_type="image/jpeg",
        )
        db.add(file)
        await db.flush()

        pa = PhotoAsset(
            file_id=file.id,
            workspace_id=workspace_id,
            face_count=5,  # non-zero to verify zeroing
        )
        db.add(pa)
        photos.append(pa)
    await db.flush()

    # Clusters
    clusters = []
    for i in range(n_clusters):
        c = FaceCluster(
            workspace_id=workspace_id,
            member_count=0,
            cluster_state="unconfirmed",
        )
        db.add(c)
        clusters.append(c)
    await db.flush()

    # Detections (round-robin assign to clusters if any, else NULL)
    detections = []
    for i in range(n_detections):
        det = FaceDetection(
            workspace_id=workspace_id,
            photo_asset_id=photos[i].id,
            bbox_json={"x": 0, "y": 0, "w": 100, "h": 100},
            embedding_encrypted=b"opaque-ciphertext-bytes-for-test",
            embedding_dim=512,
            detector_version="test-detector",
            recognizer_version="test-recognizer",
            cluster_id=clusters[i % n_clusters].id if n_clusters else None,
            detection_score=0.9,
            qdrant_point_id=uuid4(),
        )
        db.add(det)
        detections.append(det)
    await db.flush()

    return photos, clusters, detections


# ── Happy path ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDeleteAllFaceDataHappyPath:
    async def test_deletes_all_detections_and_clusters(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=100, n_clusters=10,
            )
            await db.commit()

        qdrant_mock = _make_qdrant_mock(remaining_after_delete=0)

        async with test_session_factory() as db:
            report = await delete_all_face_data(
                workspace_id=workspace_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        assert report.detection_count == 100
        assert report.cluster_count == 10
        assert report.duration_ms >= 0

        # All gone
        async with test_session_factory() as db:
            det_count = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == workspace_id
                    )
                )
            ).all()
            cluster_count = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.workspace_id == workspace_id
                    )
                )
            ).all()
        assert len(det_count) == 0
        assert len(cluster_count) == 0

    async def test_zeros_photo_asset_face_count(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=5, n_clusters=2,
            )
            await db.commit()

        qdrant_mock = _make_qdrant_mock()
        async with test_session_factory() as db:
            await delete_all_face_data(
                workspace_id=workspace_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        async with test_session_factory() as db:
            photos = (
                await db.execute(
                    select(PhotoAsset).where(PhotoAsset.workspace_id == workspace_id)
                )
            ).scalars().all()

        assert len(photos) > 0
        for p in photos:
            assert p.face_count == 0

    async def test_emits_audit_row_with_counts_and_duration(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=7, n_clusters=3,
            )
            await db.commit()

        qdrant_mock = _make_qdrant_mock()
        async with test_session_factory() as db:
            await delete_all_face_data(
                workspace_id=workspace_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        async with test_session_factory() as db:
            audit_rows = (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.workspace_id == workspace_id,
                        AuditLog.action == "face_data_hard_deleted",
                    )
                )
            ).scalars().all()

        assert len(audit_rows) == 1
        row = audit_rows[0]
        assert row.metadata_json["detection_count"] == 7
        assert row.metadata_json["cluster_count"] == 3
        assert row.metadata_json["detection_count_before"] == 7
        assert row.metadata_json["cluster_count_before"] == 3
        assert row.metadata_json["duration_ms"] >= 0

    async def test_qdrant_delete_called_with_workspace_filter(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        """Qdrant delete must target ONLY this workspace."""
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=2, n_clusters=1,
            )
            await db.commit()

        qdrant_mock = _make_qdrant_mock()
        async with test_session_factory() as db:
            await delete_all_face_data(
                workspace_id=workspace_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        qdrant_mock.delete.assert_called_once()
        call = qdrant_mock.delete.call_args
        assert call.kwargs["collection_name"] == "face_embeddings"
        selector = call.kwargs["points_selector"]
        # FilterSelector wraps a Filter; the workspace_id must appear in must clause
        filter_must = selector.filter.must
        assert any(
            getattr(cond, "key", None) == "workspace_id"
            and getattr(cond.match, "value", None) == str(workspace_id)
            for cond in filter_must
        )

    async def test_qdrant_verify_called_after_delete(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=1, n_clusters=1,
            )
            await db.commit()

        qdrant_mock = _make_qdrant_mock()
        async with test_session_factory() as db:
            await delete_all_face_data(
                workspace_id=workspace_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        qdrant_mock.count.assert_called_once()
        call = qdrant_mock.count.call_args
        assert call.kwargs["collection_name"] == "face_embeddings"
        assert call.kwargs["exact"] is True

    async def test_empty_workspace_succeeds_with_zero_counts(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        """No seeded data — delete still completes and reports zeros."""
        qdrant_mock = _make_qdrant_mock()
        async with test_session_factory() as db:
            report = await delete_all_face_data(
                workspace_id=workspace_id, db=db, qdrant=qdrant_mock
            )
            await db.commit()

        assert report.detection_count == 0
        assert report.cluster_count == 0


# ── Failure paths ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDeleteAllFaceDataFailures:
    async def test_qdrant_delete_raises_propagates(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=1, n_clusters=1,
            )
            await db.commit()

        qdrant_mock = AsyncMock()
        qdrant_mock.delete = AsyncMock(side_effect=RuntimeError("qdrant down"))

        async with test_session_factory() as db:
            with pytest.raises(ServiceUnavailableError) as exc:
                await delete_all_face_data(
                    workspace_id=workspace_id, db=db, qdrant=qdrant_mock
                )
            await db.rollback()
        assert exc.value.error_code == "FACE_HARD_DELETE_QDRANT_FAILED"

        # Detections still present because PG step never ran
        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == workspace_id
                    )
                )
            ).all()
        assert len(rows) == 1

    async def test_qdrant_verify_nonzero_raises_residue(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=1, n_clusters=1,
            )
            await db.commit()

        # Qdrant "succeeded" but verify reports 3 remaining points
        qdrant_mock = _make_qdrant_mock(remaining_after_delete=3)

        async with test_session_factory() as db:
            with pytest.raises(ServiceUnavailableError) as exc:
                await delete_all_face_data(
                    workspace_id=workspace_id, db=db, qdrant=qdrant_mock
                )
            await db.rollback()
        assert exc.value.error_code == "FACE_HARD_DELETE_QDRANT_RESIDUE"

        # PG still intact (caller will roll back)
        async with test_session_factory() as db:
            rows = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == workspace_id
                    )
                )
            ).all()
        assert len(rows) == 1

    async def test_qdrant_count_raises_propagates(
        self, test_session_factory, workspace_id, seed_user_id
    ):
        async with test_session_factory() as db:
            await _seed_face_data(
                db, workspace_id, registered_by=seed_user_id,
                n_detections=1, n_clusters=1,
            )
            await db.commit()

        qdrant_mock = AsyncMock()
        qdrant_mock.delete = AsyncMock(return_value=None)
        qdrant_mock.count = AsyncMock(side_effect=RuntimeError("network blip"))

        async with test_session_factory() as db:
            with pytest.raises(ServiceUnavailableError) as exc:
                await delete_all_face_data(
                    workspace_id=workspace_id, db=db, qdrant=qdrant_mock
                )
            await db.rollback()
        assert exc.value.error_code == "FACE_HARD_DELETE_QDRANT_VERIFY_FAILED"
