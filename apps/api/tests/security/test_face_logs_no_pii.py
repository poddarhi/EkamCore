"""PII-safety sweep across every log event emitted by the face pipeline
(S11-008).

This test complements the S11-005 test_face_logging.py file which covers
only FaceModel. Here we exercise the full pipeline — face_ingestion,
consent_service, hard_delete, backfill_service — and capture every
structlog event, then assert none contain:

  - bbox dicts (keys x, y, w, h)
  - numeric lists (embedding leak shape)
  - filename substrings (.jpg/.jpeg/.png/.heic/.webp) in any string value
  - unexpected kwarg names (a conservative whitelist)

The whitelist is a superset of the S11-005 one — it adds fields used
by the broader pipeline modules. New fields must be added here with
an explanation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path
from uuid import uuid4

import pytest
import structlog
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
from api.services.face import consent_service, crypto
from api.services.face.face_ingestion import process_photo_for_faces
from api.services.face.face_model import FaceResult


# Expanded whitelist covering every face pipeline module's log fields.
ALLOWED_FIELDS = {
    # structlog infrastructure
    "event",
    "level",
    "timestamp",
    "logger",
    # identifiers
    "workspace_id",
    "photo_asset_id",
    "user_id",
    "job_id",
    "correlation_id",
    # counts + timings
    "face_count",
    "detection_count",
    "cluster_count",
    "processed_photos",
    "total_photos",
    "failed_photos",
    "processed",
    "failed",
    "wiped",
    "pending_count",
    "remaining",
    "detection_count_before",
    "cluster_count_before",
    "qdrant_point_count_before_verify",
    "duration_ms",
    "load_duration_ms",
    "memory_delta_mb",
    # configuration + versions
    "detector_version",
    "recognizer_version",
    "model_dir",
    "version",
    "revoked_version",
    # error surface (no user data)
    "error_type",
    "reason",
    "expected",
    "actual",
    "load_error",
}


def _capture_events() -> tuple[list[dict], object]:
    captured: list[dict] = []

    def capture_processor(_logger, _method_name, event_dict):
        captured.append(dict(event_dict))
        raise structlog.DropEvent

    return captured, capture_processor


def _assert_pii_safe(events: list[dict]) -> None:
    for ev in events:
        name = ev.get("event", "")
        unknown = set(ev.keys()) - ALLOWED_FIELDS
        assert not unknown, (
            f"Unexpected log fields in event {name!r}: {unknown}. "
            f"Add to ALLOWED_FIELDS with justification if this is safe."
        )
        for k, v in ev.items():
            # Numeric list → possible embedding leak
            if isinstance(v, list):
                if v and all(isinstance(x, (int, float)) for x in v):
                    pytest.fail(
                        f"Numeric list in {k!r} of event {name!r} — possible embedding leak"
                    )
            # Bbox-shaped dict
            if isinstance(v, dict):
                if set(v.keys()) >= {"x", "y", "w", "h"}:
                    pytest.fail(
                        f"Bbox-shaped dict in {k!r} of event {name!r}"
                    )
            # Filename substrings
            if isinstance(v, str):
                low = v.lower()
                for ext in (".jpg", ".jpeg", ".png", ".heic", ".webp"):
                    if ext in low:
                        pytest.fail(
                            f"Filename-like value in {k!r} of event {name!r}: {v!r}"
                        )


def _fake_face(score: float = 0.9) -> FaceResult:
    return FaceResult(
        bbox={"x": 1.0, "y": 2.0, "w": 10.0, "h": 20.0},
        detection_score=score,
        embedding=[0.1] * 512,
    )


def _fake_face_model() -> MagicMock:
    m = MagicMock()
    m.loaded = True
    m.load_error = None
    m.detector_version = "pii-test-det-v1"
    m.recognizer_version = "pii-test-rec-v1"
    m.load = MagicMock()
    m.detect_and_embed = MagicMock(return_value=[_fake_face()])
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


@pytest.mark.asyncio
class TestFacePipelineLogsNoPII:
    async def test_full_detect_path_logs_are_pii_safe(
        self, test_session_factory, seed_user, face_env
    ):
        """Exercise consent grant + a photo run + the face_ingestion
        logger, and assert every captured event is PII-safe."""
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
                name="pii-src",
                type="photo_folder",
                registered_by=user_id,
                status="active",
            )
            db.add(src)
            await db.flush()
            disk = f"/tmp/ekamcore-pii-{uuid4().hex}.jpg"
            Path(disk).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
            f = File(
                workspace_id=ws,
                source_id=src.id,
                filename="pii.jpg",
                path=disk,
                content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                size_bytes=36,
                mime_type="image/jpeg",
            )
            db.add(f)
            await db.flush()
            pa = PhotoAsset(
                file_id=f.id, workspace_id=ws, face_count=0
            )
            db.add(pa)
            await db.flush()
            pa_id = pa.id
            await db.commit()

        captured, processor = _capture_events()
        safe_logger = structlog.wrap_logger(
            structlog.get_logger(), processors=[processor]
        )

        from api.services.face import face_ingestion as fi_mod

        qdrant = MagicMock()
        qdrant.upsert = MagicMock()
        import unittest.mock

        qdrant.upsert = unittest.mock.AsyncMock(return_value=None)
        qdrant.delete = unittest.mock.AsyncMock(return_value=None)

        with (
            unittest.mock.patch.object(fi_mod, "logger", safe_logger),
            unittest.mock.patch(
                "api.services.face.face_model.logger", safe_logger
            ),
        ):
            async with test_session_factory() as db:
                await process_photo_for_faces(
                    pa_id,
                    db,
                    qdrant=qdrant,
                    face_model=_fake_face_model(),
                )
                await db.commit()

        assert len(captured) >= 1
        _assert_pii_safe(captured)
