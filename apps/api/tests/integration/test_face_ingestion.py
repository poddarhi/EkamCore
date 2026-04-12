"""Integration tests for face_ingestion.process_photo_for_faces (S11-006).

These tests use a real Postgres database (via ``test_session_factory``)
but mock the FaceModel singleton and the Qdrant client. A fake JPEG is
written to /tmp so the File.path read succeeds without requiring a
real image — the mocked face model ignores the bytes anyway.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
from api.services.face import consent_service, crypto
from api.services.face.face_model import FaceResult


# ── Fake helpers ───────────────────────────────────────────────────────────


def _fake_face(score: float = 0.92) -> FaceResult:
    return FaceResult(
        bbox={"x": 10.0, "y": 20.0, "w": 100.0, "h": 120.0},
        detection_score=score,
        embedding=[0.1] * 512,
    )


def _fake_face_model(faces: list[FaceResult]) -> MagicMock:
    model = MagicMock()
    model.loaded = True
    model.load_error = None
    model.detector_version = "test-detector-v1"
    model.recognizer_version = "test-recognizer-v1"
    model.load = MagicMock()
    model.detect_and_embed = MagicMock(return_value=faces)
    return model


def _fake_qdrant() -> AsyncMock:
    m = AsyncMock()
    m.upsert = AsyncMock(return_value=None)
    m.delete = AsyncMock(return_value=None)
    return m


async def _seed_photo(
    db,
    workspace_id,
    *,
    registered_by,
    name_prefix: str = "face-ing",
) -> tuple[File, PhotoAsset, str]:
    """Create a Source + File + PhotoAsset with a real tiny file on disk."""
    src = Source(
        workspace_id=workspace_id,
        name=f"{name_prefix}-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=registered_by,
        status="active",
    )
    db.add(src)
    await db.flush()

    # Real tiny file so Path(...).read_bytes() succeeds. Bytes don't
    # matter — the mocked face model ignores them.
    disk_path = f"/tmp/ekamcore-{name_prefix}-{uuid4().hex}.jpg"
    Path(disk_path).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    f = File(
        workspace_id=workspace_id,
        source_id=src.id,
        filename=Path(disk_path).name,
        path=disk_path,
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=104,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()

    pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=0)
    db.add(pa)
    await db.flush()
    return f, pa, disk_path


@pytest.fixture
def face_env():
    """Enable flag + real Fernet key so encrypt_embedding succeeds."""
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


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestProcessPhotoForFaces:
    async def test_consent_active_inserts_row_and_upserts_qdrant(
        self, test_session_factory, seed_user, face_env
    ):
        from api.services.face.face_ingestion import process_photo_for_faces

        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            _, pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        qdrant = _fake_qdrant()
        face_model = _fake_face_model([_fake_face(0.92)])

        async with test_session_factory() as db:
            count = await process_photo_for_faces(
                pa_id, db, qdrant=qdrant, face_model=face_model
            )
            await db.commit()

        assert count == 1

        # Qdrant upsert carried workspace_id in the payload
        qdrant.upsert.assert_awaited_once()
        call_kwargs = qdrant.upsert.await_args.kwargs
        assert call_kwargs["collection_name"] == "face_embeddings"
        points = call_kwargs["points"]
        assert len(points) == 1
        assert points[0].payload["workspace_id"] == str(ws)
        assert points[0].payload["photo_asset_id"] == str(pa_id)
        assert points[0].payload["detector_version"] == "test-detector-v1"

        async with test_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.photo_asset_id == pa_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            refreshed_pa = (
                await db.execute(
                    select(PhotoAsset).where(PhotoAsset.id == pa_id)
                )
            ).scalar_one()

        assert len(rows) == 1
        assert rows[0].workspace_id == ws
        assert rows[0].detection_score == pytest.approx(0.92, abs=1e-4)
        assert rows[0].detector_version == "test-detector-v1"
        assert rows[0].embedding_encrypted  # non-empty ciphertext
        assert refreshed_pa.face_count == 1

    async def test_consent_inactive_returns_zero_and_writes_nothing(
        self, test_session_factory, seed_user, face_env
    ):
        from api.services.face.face_ingestion import process_photo_for_faces

        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        # NOTE: consent is NOT granted
        async with test_session_factory() as db:
            _, pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        qdrant = _fake_qdrant()
        face_model = _fake_face_model([_fake_face()])
        async with test_session_factory() as db:
            count = await process_photo_for_faces(
                pa_id, db, qdrant=qdrant, face_model=face_model
            )
            await db.commit()

        assert count == 0
        face_model.detect_and_embed.assert_not_called()
        qdrant.upsert.assert_not_called()

        async with test_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.photo_asset_id == pa_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            refreshed = (
                await db.execute(
                    select(PhotoAsset).where(PhotoAsset.id == pa_id)
                )
            ).scalar_one()
        assert rows == []
        assert refreshed.face_count == 0

    async def test_midflight_revocation_blocks_writes(
        self, test_session_factory, seed_user, face_env
    ):
        """Queue photo while consent active, revoke, then run worker."""
        from api.services.face.face_ingestion import process_photo_for_faces

        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            _, pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        # Revoke — hard_delete wipes any existing face data via Qdrant
        revoke_qdrant = _fake_qdrant()
        # Also stub count so data_erasure sees zero residual points
        cr = MagicMock()
        cr.count = 0
        revoke_qdrant.count = AsyncMock(return_value=cr)
        async with test_session_factory() as db:
            with patch(
                "api.services.face.hard_delete.get_qdrant",
                return_value=revoke_qdrant,
            ):
                await consent_service.revoke(
                    workspace_id=ws,
                    user_id=user_id,
                    ip="127.0.0.1",
                    user_agent="pytest",
                    db=db,
                )
                await db.commit()

        # Now run the worker — must short-circuit
        qdrant = _fake_qdrant()
        face_model = _fake_face_model([_fake_face()])
        async with test_session_factory() as db:
            count = await process_photo_for_faces(
                pa_id, db, qdrant=qdrant, face_model=face_model
            )
            await db.commit()

        assert count == 0
        face_model.detect_and_embed.assert_not_called()
        qdrant.upsert.assert_not_called()

    async def test_rerun_is_idempotent(
        self, test_session_factory, seed_user, face_env
    ):
        from api.services.face.face_ingestion import process_photo_for_faces

        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            _, pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        qdrant = _fake_qdrant()
        face_model = _fake_face_model([_fake_face(0.82), _fake_face(0.91)])

        async with test_session_factory() as db:
            first = await process_photo_for_faces(
                pa_id, db, qdrant=qdrant, face_model=face_model
            )
            await db.commit()
        async with test_session_factory() as db:
            second = await process_photo_for_faces(
                pa_id, db, qdrant=qdrant, face_model=face_model
            )
            await db.commit()

        assert first == 2
        assert second == 2

        async with test_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.photo_asset_id == pa_id,
                            FaceDetection.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
        # Exactly 2 rows — the second run wiped the first set before
        # inserting, so we don't end up with 4.
        assert len(rows) == 2
        # Idempotent wipe must have called qdrant.delete at least once
        # (during the second run, to clean up the first run's points).
        assert qdrant.delete.await_count >= 1

    async def test_no_faces_found_yields_zero_count(
        self, test_session_factory, seed_user, face_env
    ):
        from api.services.face.face_ingestion import process_photo_for_faces

        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            _, pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        qdrant = _fake_qdrant()
        face_model = _fake_face_model([])  # zero faces detected
        async with test_session_factory() as db:
            count = await process_photo_for_faces(
                pa_id, db, qdrant=qdrant, face_model=face_model
            )
            await db.commit()

        assert count == 0
        qdrant.upsert.assert_not_called()

        async with test_session_factory() as db:
            refreshed = (
                await db.execute(
                    select(PhotoAsset).where(PhotoAsset.id == pa_id)
                )
            ).scalar_one()
        assert refreshed.face_count == 0
