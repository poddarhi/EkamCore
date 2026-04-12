"""Unit tests for api.services.face.face_model (S11-005).

Three tiers:

  Tier 1 — shape contract (always runs, fully mocked)
  Tier 2 — error paths (always runs, fully mocked)
  Tier 3 — real model integration (skipped unless
           tests/fixtures/face/face_test_001.jpg + INSIGHTFACE_MODEL_DIR
           + insightface Python package are all present)
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from api.errors import (
    FaceModelInvalidImageError,
    FaceModelNotLoadedError,
)
from api.services.face import face_model as face_model_module
from api.services.face.face_config import (
    DETECTOR_VERSION,
    EMBEDDING_DIM,
    RECOGNIZER_VERSION,
)
from api.services.face.face_model import FaceModel, FaceResult


class _FakeCv2:
    """Minimal stand-in for opencv-python-headless.

    S11-005 scope constraint: the project has not yet ``poetry install``ed
    opencv in the dev environment, so these unit tests use a tiny fake
    that implements just the two symbols face_model.detect_and_embed
    touches (``imdecode`` and ``IMREAD_COLOR``). Tests that simulate a
    successful decode feed image bytes that start with a known header
    (PNG or JPEG); tests that simulate decode failure pass bytes that
    don't, and the fake returns None — mirroring the real cv2 behavior.
    """

    IMREAD_COLOR = 1

    @staticmethod
    def imdecode(buf: np.ndarray, _flags: int) -> np.ndarray | None:
        raw = bytes(buf.tobytes())
        if raw.startswith(b"\x89PNG") or raw.startswith(b"\xff\xd8\xff"):
            # Return a 10x10x3 BGR image. Values are irrelevant because
            # self._app.get() is mocked in every test that reaches here.
            return np.zeros((10, 10, 3), dtype=np.uint8)
        return None


@pytest.fixture(autouse=True)
def _reset_face_model_singleton():
    """Isolate each test: drop the module-level singleton both before
    and after the test body runs, so one test's mocked state doesn't
    bleed into the next. Also clears the cached _cv2/_np pointers."""
    FaceModel._reset()
    face_model_module._cv2 = None
    face_model_module._np = None
    yield
    FaceModel._reset()
    face_model_module._cv2 = None
    face_model_module._np = None


@pytest.fixture
def fake_cv2_and_numpy(monkeypatch: pytest.MonkeyPatch):
    """Pre-populate ``face_model._cv2`` / ``_np`` with fakes so
    ``detect_and_embed`` skips the real opencv import."""
    fake = _FakeCv2()
    monkeypatch.setattr(face_model_module, "_cv2", fake)
    monkeypatch.setattr(face_model_module, "_np", np)
    return fake


# ── Tier 1 — singleton + shape contract ─────────────────────────────────


class TestSingleton:
    def test_instance_returns_same_object_on_repeated_calls(self):
        a = FaceModel.instance()
        b = FaceModel.instance()
        assert a is b

    def test_reset_drops_the_singleton(self):
        a = FaceModel.instance()
        FaceModel._reset()
        b = FaceModel.instance()
        assert a is not b

    def test_fresh_instance_is_not_loaded(self):
        m = FaceModel.instance()
        assert m.loaded is False
        assert m.load_error is None

    def test_versions_are_exposed_even_before_load(self):
        m = FaceModel.instance()
        assert m.detector_version == DETECTOR_VERSION
        assert m.recognizer_version == RECOGNIZER_VERSION


class TestDetectAndEmbedContract:
    def _make_fake_face(self, score: float = 0.92):
        """Build a fake insightface Face with ndarray-like attributes."""
        import numpy as np  # available via pillow, no extra install

        face = MagicMock()
        face.bbox = np.array([10.0, 20.0, 110.0, 140.0])  # x1,y1,x2,y2
        face.det_score = np.float32(score)
        face.normed_embedding = np.full((EMBEDDING_DIM,), 0.1, dtype=np.float32)
        return face

    def test_detect_and_embed_raises_when_not_loaded(self):
        m = FaceModel.instance()
        with pytest.raises(FaceModelNotLoadedError):
            m.detect_and_embed(b"fake-image-bytes")

    def test_load_is_idempotent_on_import_failure(self):
        """If `insightface` cannot be imported, load() sets _load_error
        and does NOT raise. Subsequent loads remain silent no-ops."""
        m = FaceModel.instance()

        def _raise_on_import(*_args, **_kwargs):
            raise ModuleNotFoundError("insightface not installed")

        # Patch the builtin __import__ selectively
        with patch("builtins.__import__", side_effect=_raise_on_import):
            m.load()
            m.load()  # second call is a no-op

        assert m.loaded is False
        assert m.load_error is not None
        assert "insightface" in m.load_error.lower() or "import" in m.load_error.lower()

    def test_detect_and_embed_happy_path_returns_face_result(self, fake_cv2_and_numpy):
        """Fully-mocked inference: one face in, one FaceResult out."""
        m = FaceModel.instance()
        # Manually mark the singleton as loaded with a mocked _app
        mock_app = MagicMock()
        mock_app.get = MagicMock(return_value=[self._make_fake_face(0.95)])
        m._app = mock_app
        m._loaded = True

        # Build a real tiny image via numpy + cv2 so OpenCV decode works.
        # 10x10 black PNG via pillow (available in the project deps).
        from io import BytesIO

        from PIL import Image as PILImage

        img = PILImage.new("RGB", (10, 10), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        results = m.detect_and_embed(
            image_bytes, photo_asset_id=uuid4()
        )

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, FaceResult)
        assert set(r.bbox.keys()) == {"x", "y", "w", "h"}
        assert r.bbox["x"] == pytest.approx(10.0)
        assert r.bbox["y"] == pytest.approx(20.0)
        assert r.bbox["w"] == pytest.approx(100.0)  # 110 - 10
        assert r.bbox["h"] == pytest.approx(120.0)  # 140 - 20
        assert r.detection_score == pytest.approx(0.95, abs=1e-3)
        assert isinstance(r.embedding, list)
        assert len(r.embedding) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in r.embedding)

    def test_detect_and_embed_skips_faces_with_no_embedding(self, fake_cv2_and_numpy):
        from io import BytesIO
        from PIL import Image as PILImage

        m = FaceModel.instance()
        # Two faces: one with embedding, one without
        good = self._make_fake_face(0.9)
        bad = MagicMock()
        bad.bbox = np.array([0.0, 0.0, 50.0, 50.0])
        bad.det_score = np.float32(0.6)
        bad.normed_embedding = None
        mock_app = MagicMock()
        mock_app.get = MagicMock(return_value=[good, bad])
        m._app = mock_app
        m._loaded = True

        img = PILImage.new("RGB", (10, 10))
        buf = BytesIO()
        img.save(buf, format="PNG")
        results = m.detect_and_embed(buf.getvalue())
        assert len(results) == 1  # only the good face


# ── Tier 2 — error paths ────────────────────────────────────────────────


class TestErrorPaths:
    def test_invalid_image_bytes_raise_invalid_image_error(self, fake_cv2_and_numpy):
        m = FaceModel.instance()
        # Mark as loaded so we actually exercise the decode path
        mock_app = MagicMock()
        m._app = mock_app
        m._loaded = True

        with pytest.raises(FaceModelInvalidImageError):
            m.detect_and_embed(b"not-an-image")

    def test_detect_raises_not_loaded_even_if_app_truthy(self):
        """Defense in depth: if _loaded is False, we refuse even if
        someone has accidentally set _app."""
        m = FaceModel.instance()
        m._app = MagicMock()
        m._loaded = False
        with pytest.raises(FaceModelNotLoadedError):
            m.detect_and_embed(b"any")


class TestStatusDict:
    def test_status_dict_unloaded_shape(self):
        m = FaceModel.instance()
        d = m.status_dict()
        assert d["loaded"] is False
        assert d["load_error"] is None
        assert d["detector_version"] == DETECTOR_VERSION
        assert d["recognizer_version"] == RECOGNIZER_VERSION
        assert d["load_duration_ms"] is None
        assert d["memory_delta_mb"] is None


# ── Tier 3 — real integration (skipped by default) ─────────────────────


def _integration_skip_reason() -> str | None:
    """Return None if the integration test can run, or a skip message."""
    model_dir = os.environ.get("INSIGHTFACE_MODEL_DIR", "")
    if not model_dir or not Path(model_dir).exists():
        return f"INSIGHTFACE_MODEL_DIR unset or missing (got: {model_dir!r})"
    fixture = Path(__file__).resolve().parent / "fixtures" / "face" / "face_test_001.jpg"
    if not fixture.exists():
        return f"fixture image missing: {fixture}"
    try:
        import insightface  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return f"insightface import failed: {type(exc).__name__}"
    return None


@pytest.mark.requires_insightface_models
class TestRealModelIntegration:
    def test_real_model_detects_face(self):
        reason = _integration_skip_reason()
        if reason:
            pytest.skip(reason)

        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "face"
            / "face_test_001.jpg"
        )
        image_bytes = fixture.read_bytes()

        m = FaceModel.instance()
        m.load()
        assert m.loaded is True, f"load failed: {m.load_error}"

        results = m.detect_and_embed(image_bytes)
        assert len(results) >= 1, "expected ≥1 face in the test fixture"

        top = max(results, key=lambda r: r.detection_score)
        assert top.detection_score > 0.5
        assert len(top.embedding) == EMBEDDING_DIM
