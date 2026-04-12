"""Workspace isolation for face ingestion (S11-006).

Two consented workspaces each ingest a face photo through
``process_photo_for_faces``. Workspace A's face_detections row must be
tagged with workspace_id=A, and the Qdrant point upsert for that photo
must carry workspace_id=A in the payload (never B). And vice versa.

This is a positive-control partner to S11-003's hard-delete isolation
test: hard-delete verifies *removal* is isolated; this test verifies
*creation* is isolated.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.face import consent_service, crypto
from api.services.face.face_model import FaceResult


def _fake_face(score: float = 0.9) -> FaceResult:
    return FaceResult(
        bbox={"x": 0.0, "y": 0.0, "w": 50.0, "h": 50.0},
        detection_score=score,
        embedding=[0.05] * 512,
    )


def _fake_face_model(faces: list[FaceResult]) -> MagicMock:
    m = MagicMock()
    m.loaded = True
    m.load_error = None
    m.detector_version = "iso-det-v1"
    m.recognizer_version = "iso-rec-v1"
    m.load = MagicMock()
    m.detect_and_embed = MagicMock(return_value=faces)
    return m


def _fake_qdrant() -> AsyncMock:
    m = AsyncMock()
    m.upsert = AsyncMock(return_value=None)
    m.delete = AsyncMock(return_value=None)
    return m


async def _make_workspace(db, owner_id: UUID, name: str) -> Workspace:
    ws = Workspace(name=name, type="personal", owner_id=owner_id)
    db.add(ws)
    await db.flush()
    db.add(
        WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role="admin")
    )
    await db.flush()
    return ws


async def _seed_photo(
    db,
    workspace_id: UUID,
    *,
    registered_by: UUID,
    label: str,
) -> PhotoAsset:
    src = Source(
        workspace_id=workspace_id,
        name=f"iso-{label}-src",
        type="photo_folder",
        registered_by=registered_by,
        status="active",
    )
    db.add(src)
    await db.flush()

    disk_path = f"/tmp/ekamcore-iso-{label}-{uuid4().hex}.jpg"
    Path(disk_path).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)

    f = File(
        workspace_id=workspace_id,
        source_id=src.id,
        filename=Path(disk_path).name,
        path=disk_path,
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=36,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()

    pa = PhotoAsset(
        file_id=f.id, workspace_id=workspace_id, face_count=0
    )
    db.add(pa)
    await db.flush()
    return pa


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


@pytest.mark.asyncio
class TestFaceWorkspaceIsolation:
    async def test_two_consented_workspaces_do_not_leak_face_data(
        self, test_session_factory, seed_user, face_env
    ):
        user_id = seed_user["user_id"]

        # Two workspaces, each consented independently
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
                user_agent="pytest",
                db=db,
            )
            await consent_service.grant(
                workspace_id=ws_b_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            pa_a = await _seed_photo(
                db, ws_a_id, registered_by=user_id, label="a"
            )
            pa_b = await _seed_photo(
                db, ws_b_id, registered_by=user_id, label="b"
            )
            pa_a_id = pa_a.id
            pa_b_id = pa_b.id
            await db.commit()

        # Process each photo with its own fake qdrant so we can inspect
        # the exact payloads that would have gone across the wire.
        qdrant_a = _fake_qdrant()
        qdrant_b = _fake_qdrant()
        face_model = _fake_face_model([_fake_face(0.9)])

        from api.services.face.face_ingestion import process_photo_for_faces

        async with test_session_factory() as db:
            count_a = await process_photo_for_faces(
                pa_a_id, db, qdrant=qdrant_a, face_model=face_model
            )
            await db.commit()
        async with test_session_factory() as db:
            count_b = await process_photo_for_faces(
                pa_b_id, db, qdrant=qdrant_b, face_model=face_model
            )
            await db.commit()

        assert count_a == 1
        assert count_b == 1

        # Qdrant payload for workspace A carries ONLY ws_a_id, not ws_b_id
        a_points = qdrant_a.upsert.await_args.kwargs["points"]
        assert len(a_points) == 1
        assert a_points[0].payload["workspace_id"] == str(ws_a_id)
        assert a_points[0].payload["workspace_id"] != str(ws_b_id)

        b_points = qdrant_b.upsert.await_args.kwargs["points"]
        assert len(b_points) == 1
        assert b_points[0].payload["workspace_id"] == str(ws_b_id)
        assert b_points[0].payload["workspace_id"] != str(ws_a_id)

        # PG isolation: each workspace's face_detections filter returns
        # only its own rows, and no row bleeds across the boundary.
        async with test_session_factory() as db:
            a_rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws_a_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            b_rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws_b_id
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert len(a_rows) == 1
        assert len(b_rows) == 1
        assert a_rows[0].photo_asset_id == pa_a_id
        assert b_rows[0].photo_asset_id == pa_b_id
        # No row from A has workspace_id == B
        assert all(r.workspace_id == ws_a_id for r in a_rows)
        assert all(r.workspace_id == ws_b_id for r in b_rows)
        # Rows are disjoint — no shared ids
        a_ids = {r.id for r in a_rows}
        b_ids = {r.id for r in b_rows}
        assert a_ids.isdisjoint(b_ids)

    async def test_consent_in_a_does_not_enable_pipeline_in_b(
        self, test_session_factory, seed_user, face_env
    ):
        """Consent on workspace A must NOT let B's photos be processed."""
        from api.services.face.face_ingestion import process_photo_for_faces

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
                user_agent="pytest",
                db=db,
            )
            # Note: no grant for ws_b
            pa_b = await _seed_photo(
                db, ws_b_id, registered_by=user_id, label="b"
            )
            pa_b_id = pa_b.id
            await db.commit()

        qdrant_b = _fake_qdrant()
        face_model = _fake_face_model([_fake_face()])
        async with test_session_factory() as db:
            count_b = await process_photo_for_faces(
                pa_b_id, db, qdrant=qdrant_b, face_model=face_model
            )
            await db.commit()

        assert count_b == 0
        face_model.detect_and_embed.assert_not_called()
        qdrant_b.upsert.assert_not_called()

        async with test_session_factory() as db:
            b_rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws_b_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert b_rows == []
