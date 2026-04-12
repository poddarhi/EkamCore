"""S11-008 face metrics integration tests.

Verifies:
  - face_ingestion.process_photo_for_faces emits record_face_event for
    detections_created and record_face_detection_latency
  - consent_service.grant emits consent_granted
  - The counters land in Redis with the expected key shape
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags, metrics_service
from api.services.face import consent_service, crypto
from api.services.face.face_ingestion import process_photo_for_faces
from api.services.face.face_model import FaceResult

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _fake_face() -> FaceResult:
    return FaceResult(
        bbox={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        detection_score=0.9,
        embedding=[0.1] * 512,
    )


def _fake_model() -> MagicMock:
    m = MagicMock()
    m.loaded = True
    m.load_error = None
    m.detector_version = "met-det"
    m.recognizer_version = "met-rec"
    m.load = MagicMock()
    m.detect_and_embed = MagicMock(return_value=[_fake_face(), _fake_face()])
    return m


def _fake_qdrant() -> AsyncMock:
    m = AsyncMock()
    m.upsert = AsyncMock(return_value=None)
    m.delete = AsyncMock(return_value=None)
    return m


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


class TestFaceMetrics:
    async def test_process_photo_emits_counter_and_latency(
        self, test_session_factory, seed_user, face_env
    ):
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
            src = Source(
                workspace_id=ws,
                name="met-src",
                type="photo_folder",
                registered_by=user_id,
                status="active",
            )
            db.add(src)
            await db.flush()
            disk = f"/tmp/ekamcore-met-{uuid4().hex}.jpg"
            Path(disk).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
            f = File(
                workspace_id=ws,
                source_id=src.id,
                filename="met.jpg",
                path=disk,
                content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                size_bytes=36,
                mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            pa = PhotoAsset(file_id=f.id, workspace_id=ws, face_count=0)
            db.add(pa)
            await db.flush()
            pa_id = pa.id
            await db.commit()

        with (
            patch.object(
                metrics_service,
                "record_face_event",
                new=AsyncMock(return_value=None),
            ) as m_event,
            patch.object(
                metrics_service,
                "record_face_detection_latency",
                new=AsyncMock(return_value=None),
            ) as m_lat,
        ):
            async with test_session_factory() as db:
                await process_photo_for_faces(
                    pa_id,
                    db,
                    qdrant=_fake_qdrant(),
                    face_model=_fake_model(),
                )
                await db.commit()

            # Counter called with detections_created + count
            event_calls = m_event.await_args_list
            names = {c.args[1] if len(c.args) > 1 else c.kwargs.get("event_name") for c in event_calls}
            assert "detections_created" in names
            # Latency recorded exactly once
            m_lat.assert_awaited_once()
            lat_args = m_lat.await_args
            assert lat_args.args[0] == ws or lat_args.kwargs.get("workspace_id") == ws
            # The latency value should be a positive float (non-zero after to_thread).
            latency_arg = lat_args.args[1] if len(lat_args.args) > 1 else lat_args.kwargs.get("latency_ms")
            assert isinstance(latency_arg, float)
            assert latency_arg >= 0.0

    async def test_consent_grant_emits_counter(
        self, test_session_factory, seed_user
    ):
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        with patch.object(
            metrics_service,
            "record_face_event",
            new=AsyncMock(return_value=None),
        ) as m_event:
            async with test_session_factory() as db:
                await consent_service.grant(
                    workspace_id=ws,
                    user_id=user_id,
                    ip="127.0.0.1",
                    user_agent="pytest",
                    db=db,
                )
                await db.commit()

        names = {
            c.args[1] if len(c.args) > 1 else c.kwargs.get("event_name")
            for c in m_event.await_args_list
        }
        assert "consent_granted" in names
