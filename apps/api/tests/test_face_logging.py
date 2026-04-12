"""PII-safety tests for FaceModel logging (S11-005).

These tests capture every structlog event emitted during
`FaceModel.detect_and_embed` and assert that none of them leaks:
  - embedding floats (list of 512 numbers)
  - bbox coordinates (dict with x/y/w/h)
  - image bytes
  - filenames (.jpg / .jpeg / .png substring in any field)

Allowed log field names are an explicit whitelist derived from the
module-level PII-safe logging rules. Any new field added to a face_model
event MUST be added to this whitelist with an explanation.

This mirrors the pattern in tests/test_logging.py (request-logging
PII guard).
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest
import structlog
from PIL import Image as PILImage

from api.services.face import face_model as face_model_module
from api.services.face.face_config import EMBEDDING_DIM
from api.services.face.face_model import FaceModel


# Fields that face_model events are allowed to emit. Anything else is
# a potential PII leak and must be reviewed before this list changes.
ALLOWED_LOG_FIELDS = {
    # structlog infrastructure
    "event",
    "level",
    "timestamp",
    "logger",
    # identifiers (UUIDs are not PII under our threat model)
    "photo_asset_id",
    "workspace_id",
    # counts + timing only
    "face_count",
    "duration_ms",
    "load_duration_ms",
    "memory_delta_mb",
    # versions are constants, not PII
    "detector_version",
    "recognizer_version",
    # configuration that is non-sensitive
    "model_dir",
    # error surface (used on failure paths)
    "error_type",
    "reason",
    "expected",
    "actual",
}


class _FakeCv2:
    """Minimal opencv stand-in (see test_face_model.py for the rationale)."""

    IMREAD_COLOR = 1

    @staticmethod
    def imdecode(buf, _flags):
        raw = bytes(buf.tobytes())
        if raw.startswith(b"\x89PNG") or raw.startswith(b"\xff\xd8\xff"):
            return np.zeros((10, 10, 3), dtype=np.uint8)
        return None


@pytest.fixture(autouse=True)
def _reset_and_install_fakes(monkeypatch: pytest.MonkeyPatch):
    """Single autouse fixture: drop the singleton, then install the
    cv2/numpy fakes. Merging the reset + install into one fixture
    avoids a fixture-ordering bug where the reset would clobber a
    separately-installed fake."""
    FaceModel._reset()
    monkeypatch.setattr(face_model_module, "_cv2", _FakeCv2())
    monkeypatch.setattr(face_model_module, "_np", np)
    yield
    FaceModel._reset()
    face_model_module._cv2 = None
    face_model_module._np = None


def _capture_structlog() -> tuple[list[dict], object]:
    """Returns (captured list, processor) following the pattern from
    tests/test_logging.py. The processor drops the event so the normal
    logger chain doesn't fire."""
    captured: list[dict] = []

    def capture_processor(_logger, _method_name, event_dict):
        captured.append(dict(event_dict))
        raise structlog.DropEvent

    return captured, capture_processor


def _make_fake_face(score: float = 0.9):
    face = MagicMock()
    face.bbox = np.array([10.0, 20.0, 110.0, 140.0])
    face.det_score = np.float32(score)
    face.normed_embedding = np.full((EMBEDDING_DIM,), 0.1, dtype=np.float32)
    return face


def _make_small_png() -> bytes:
    img = PILImage.new("RGB", (10, 10), color=(0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _assert_pii_safe(captured: list[dict]) -> None:
    """Every captured event must satisfy the PII-safety rules."""
    for event in captured:
        # 1. No unexpected field names
        unknown = set(event.keys()) - ALLOWED_LOG_FIELDS
        assert not unknown, (
            f"Unexpected log fields leaked from face_model event "
            f"{event.get('event')!r}: {unknown}. "
            f"If this is intentional, add the field to ALLOWED_LOG_FIELDS "
            f"with a comment explaining why it's not PII."
        )

        # 2. No value is a list of floats (embedding leak check)
        for key, value in event.items():
            if isinstance(value, list):
                if value and all(isinstance(v, (int, float)) for v in value):
                    pytest.fail(
                        f"Numeric list leaked in field {key!r} of event "
                        f"{event.get('event')!r} — possible embedding leak"
                    )
            # 3. No dict value contains bbox-shaped keys
            if isinstance(value, dict):
                if set(value.keys()) >= {"x", "y", "w", "h"}:
                    pytest.fail(
                        f"Bbox-shaped dict leaked in field {key!r} of event "
                        f"{event.get('event')!r}"
                    )
            # 4. No value contains image-filename substrings
            if isinstance(value, str):
                lower = value.lower()
                for ext in (".jpg", ".jpeg", ".png", ".heic", ".webp"):
                    if ext in lower:
                        pytest.fail(
                            f"Filename-like value in field {key!r} of event "
                            f"{event.get('event')!r}: {value!r}"
                        )


class TestDetectLoggingPIISafety:
    def test_detect_event_contains_only_safe_fields(self):
        # Swap out the module logger with one using our capture
        # processor. The FaceModel module holds a reference to its
        # structlog logger at import time, so we patch that reference.
        captured, processor = _capture_structlog()
        safe_logger = structlog.wrap_logger(
            structlog.get_logger(),
            processors=[processor],
        )

        m = FaceModel.instance()
        mock_app = MagicMock()
        mock_app.get = MagicMock(return_value=[_make_fake_face(0.9), _make_fake_face(0.8)])
        m._app = mock_app
        m._loaded = True

        image_bytes = _make_small_png()

        import unittest.mock

        with unittest.mock.patch.object(
            face_model_module, "logger", safe_logger
        ):
            m.detect_and_embed(image_bytes, photo_asset_id=uuid4())

        assert len(captured) >= 1, "expected at least face_model.detected event"
        # The detected event specifically
        detect_events = [e for e in captured if e.get("event") == "face_model.detected"]
        assert len(detect_events) == 1
        ev = detect_events[0]
        assert ev["face_count"] == 2  # count, not the face objects
        assert "duration_ms" in ev

        _assert_pii_safe(captured)

    def test_detect_event_does_not_log_filenames(self):
        """Even if a caller passes an image that *happens* to have a
        .jpg byte sequence in it, the logger only sees counts + UUIDs."""
        captured, processor = _capture_structlog()
        safe_logger = structlog.wrap_logger(
            structlog.get_logger(),
            processors=[processor],
        )

        m = FaceModel.instance()
        mock_app = MagicMock()
        mock_app.get = MagicMock(return_value=[])
        m._app = mock_app
        m._loaded = True

        import unittest.mock

        with unittest.mock.patch.object(
            face_model_module, "logger", safe_logger
        ):
            m.detect_and_embed(_make_small_png(), photo_asset_id=uuid4())

        _assert_pii_safe(captured)

    def test_load_failure_event_is_pii_safe(self):
        """Even on load failure (most verbose path), no PII is emitted."""
        captured, processor = _capture_structlog()
        safe_logger = structlog.wrap_logger(
            structlog.get_logger(),
            processors=[processor],
        )

        def _raise_on_import(*_args, **_kwargs):
            raise ModuleNotFoundError("insightface not installed")

        import unittest.mock

        m = FaceModel.instance()
        with unittest.mock.patch.object(
            face_model_module, "logger", safe_logger
        ):
            with unittest.mock.patch("builtins.__import__", side_effect=_raise_on_import):
                m.load()

        # The failure log event should be present
        fail_events = [e for e in captured if "load_failed" in str(e.get("event", ""))]
        assert len(fail_events) >= 1

        _assert_pii_safe(captured)

    def test_status_dict_contains_no_pii(self):
        """status_dict() is called by /health. Must never leak PII."""
        m = FaceModel.instance()
        d = m.status_dict()
        # Whitelist shape
        allowed = {
            "loaded",
            "load_error",
            "detector_version",
            "recognizer_version",
            "load_duration_ms",
            "memory_delta_mb",
        }
        assert set(d.keys()) == allowed
