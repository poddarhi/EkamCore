"""Integration test: revoke rolls back cleanly when Qdrant is unreachable (S11-003).

The critical legal invariant: if hard_delete raises for ANY reason,
ConsentService.revoke() must NOT persist a tombstoned consent record.
The face pipeline must report as still active, and the user's face
data must be unchanged.

This test simulates a mid-revoke Qdrant outage by patching get_qdrant
to return a mock that raises on delete.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.errors import ServiceUnavailableError
from api.services.face import consent_service

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_minimal_face_data(db, workspace_id, user_id):
    src = Source(
        workspace_id=workspace_id,
        name="rb-src",
        type="photo_folder",
        registered_by=user_id,
        status="active",
    )
    db.add(src)
    await db.flush()
    f = File(
        workspace_id=workspace_id,
        source_id=src.id,
        filename="rb.jpg",
        path="/rb.jpg",
        content_hash_sha256="f" * 64,
        size_bytes=10,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()
    pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=4)
    db.add(pa)
    await db.flush()
    cluster = FaceCluster(
        workspace_id=workspace_id, member_count=0, cluster_state="unconfirmed"
    )
    db.add(cluster)
    await db.flush()
    det = FaceDetection(
        workspace_id=workspace_id,
        photo_asset_id=pa.id,
        bbox_json={"x": 0},
        embedding_encrypted=b"ct",
        embedding_dim=512,
        detector_version="v1",
        recognizer_version="v1",
        cluster_id=cluster.id,
        detection_score=0.9,
        qdrant_point_id=uuid4(),
    )
    db.add(det)
    await db.flush()


class TestRevokeRollback:
    async def test_qdrant_unreachable_leaves_consent_active_and_data_intact(
        self, test_session_factory, seed_user
    ):
        workspace_id = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        # Seed face data
        async with test_session_factory() as db:
            await _seed_minimal_face_data(db, workspace_id, user_id)
            await db.commit()

        # Grant consent
        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="test",
                db=db,
            )
            await db.commit()

        # Pre-check: consent is active
        async with test_session_factory() as db:
            active_before = await consent_service.is_consent_active(
                workspace_id, db
            )
        assert active_before is True

        # Simulate Qdrant outage: delete raises
        broken_qdrant = AsyncMock()
        broken_qdrant.delete = AsyncMock(side_effect=RuntimeError("qdrant unreachable"))

        with patch(
            "api.services.face.hard_delete.get_qdrant",
            return_value=broken_qdrant,
        ):
            async with test_session_factory() as db:
                with pytest.raises(ServiceUnavailableError) as exc:
                    await consent_service.revoke(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        ip="127.0.0.1",
                        user_agent="test",
                        db=db,
                    )
                assert exc.value.error_code == "FACE_HARD_DELETE_QDRANT_FAILED"
                # Caller must roll back to preserve pre-revoke state
                await db.rollback()

        # Clear the 60s Redis consent cache so the next read hits PG
        from api.services.face.consent_service import _cache_invalidate

        await _cache_invalidate(workspace_id)

        # Post-check: consent is STILL active
        async with test_session_factory() as db:
            active_after = await consent_service.is_consent_active(
                workspace_id, db
            )
        assert active_after is True, (
            "Consent was revoked despite hard_delete failure — rollback contract broken"
        )

        # Face data is still present
        async with test_session_factory() as db:
            dets = (
                await db.execute(
                    select(FaceDetection).where(
                        FaceDetection.workspace_id == workspace_id
                    )
                )
            ).scalars().all()
            clusters = (
                await db.execute(
                    select(FaceCluster).where(
                        FaceCluster.workspace_id == workspace_id
                    )
                )
            ).scalars().all()
            photos = (
                await db.execute(
                    select(PhotoAsset).where(
                        PhotoAsset.workspace_id == workspace_id
                    )
                )
            ).scalars().all()

        assert len(dets) == 1, "Face detections lost despite revoke rollback"
        assert len(clusters) == 1, "Face clusters lost despite revoke rollback"
        assert all(p.face_count == 4 for p in photos), (
            "photo_asset.face_count was zeroed despite revoke rollback"
        )
