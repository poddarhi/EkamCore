"""InsightFace detector + recognizer singleton (S11-005).

Lazy-loaded per-process holder for a single ``insightface.app.FaceAnalysis``
instance. One worker process = one FaceAnalysis = ~500MB RSS delta after
load. We never reload and never hold more than one copy in memory.

Design rules (ART-14, ART-15 §4, ART-27):

  1. **Fail closed.** load() captures any exception into `_load_error`
     and does NOT raise. Callers check `.loaded` before calling
     `detect_and_embed`. This way a bad model directory or a broken
     install cannot crash a worker — the worker reports "face_model
     unavailable" via /health and refuses new work gracefully.

  2. **PII-safe logging.** We log counts, timings, and version strings
     only. Never bbox coordinates, never embedding floats, never image
     bytes or filenames. test_face_logging.py enforces this with a
     whitelist of allowed log field names.

  3. **Lazy `insightface` import.** The heavy dependency
     (`insightface`, `onnxruntime`, `opencv-python-headless`) is
     imported inside `.load()`, not at module top. This lets the module
     stay importable in environments where the deps haven't been
     `poetry install`ed yet (important for existing tests that import
     every service module during SQLAlchemy model collection).

  4. **Singleton via classmethod.** `FaceModel.instance()` returns the
     per-process singleton. Tests can reset it via `FaceModel._reset()`
     when they need a clean state.

  5. **One priority slot.** detect_and_embed runs under
     `Priority.P4_BACKGROUND_LOW` in the resource controller — face
     pipeline never competes with LLM (P1/P2) or embeddings (P3). Slot
     acquisition is the caller's responsibility; this module is a
     pure compute box.

Usage (inside a worker task):

    model = FaceModel.instance()
    if not model.loaded:
        model.load()
        if not model.loaded:
            raise FaceModelLoadFailedError(...)

    async with acquire_slot(Priority.P4_BACKGROUND_LOW):
        faces = model.detect_and_embed(image_bytes, photo_asset_id=pid)
"""

from __future__ import annotations

import resource
import sys
import time
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from api.config import settings
from api.errors import (
    FaceModelInvalidImageError,
    FaceModelLoadFailedError,
    FaceModelNotLoadedError,
)
from api.services.face.face_config import (
    CTX_ID,
    DETECTION_SIZE,
    DETECTOR_VERSION,
    EMBEDDING_DIM,
    MODEL_PACK_NAME,
    PROVIDERS,
    RECOGNIZER_VERSION,
)

logger = structlog.get_logger()

# Lazy-imported heavy modules. Stored at module level so tests can
# inject fakes via monkeypatch.setattr(face_model, "_cv2", fake_cv2).
# See _ensure_cv2_numpy() for the import-on-first-use pattern.
_cv2: Any = None
_np: Any = None


def _ensure_cv2_numpy() -> None:
    """Import opencv-python-headless and numpy on first use; cache them
    on the module namespace. Tests can pre-populate `_cv2` / `_np` to
    bypass the real import entirely.

    Raises FaceModelLoadFailedError if the imports fail — callers
    should only reach this path after `.load()` has already succeeded,
    so an import failure here is a genuine install bug.
    """
    global _cv2, _np
    if _cv2 is not None and _np is not None:
        return
    try:
        import cv2 as real_cv2  # type: ignore[import-not-found]
        import numpy as real_np  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise FaceModelLoadFailedError(
            error_code="FACE_MODEL_LOAD_FAILED",
            message=(
                f"OpenCV / numpy import failed at detect time: "
                f"{type(exc).__name__}"
            ),
        ) from exc
    _cv2 = real_cv2
    _np = real_np


# ── Result shape ───────────────────────────────────────────────────────────


class FaceResult(BaseModel):
    """One detected face, fully self-contained.

    - ``bbox`` is stored as a dict (x, y, w, h) of floats, NOT as a
      numpy array. This keeps the type JSON-serializable for storage
      in face_detections.bbox_json.
    - ``embedding`` is a plain list of Python floats (length 512),
      NOT a numpy array, for the same JSON reason. Downstream callers
      re-pack it into float32 bytes via services.face.crypto.
    """

    model_config = ConfigDict(extra="forbid")

    bbox: dict[str, float] = Field(
        description="Bounding box as {x, y, w, h} in pixel coordinates.",
    )
    detection_score: float = Field(
        description="Detector confidence in [0.0, 1.0].",
    )
    embedding: list[float] = Field(
        description=f"Face embedding, length {EMBEDDING_DIM}.",
    )


# ── Memory measurement helper ──────────────────────────────────────────────


def _current_rss_bytes() -> int:
    """Return current process RSS in bytes.

    `resource.getrusage().ru_maxrss` reports kilobytes on Linux and
    bytes on macOS — normalize to bytes on both platforms.
    """
    ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(ru_maxrss)
    return int(ru_maxrss) * 1024  # Linux reports KB


# ── The singleton ──────────────────────────────────────────────────────────


class FaceModel:
    """Per-process lazy singleton wrapping an ``insightface.app.FaceAnalysis``.

    Call ``FaceModel.instance()`` to get the singleton. The first call
    to ``.load()`` initializes the underlying FaceAnalysis from the
    buffalo_l pack at ``settings.INSIGHTFACE_MODEL_DIR``. Subsequent
    loads are idempotent no-ops.

    After a successful load, ``detect_and_embed(image_bytes)`` returns
    a list of ``FaceResult``. Raises ``FaceModelNotLoadedError`` if
    called before load, ``FaceModelInvalidImageError`` if OpenCV cannot
    decode the bytes.
    """

    # Class-level singleton slot. Use _reset() in tests.
    _instance: "FaceModel | None" = None

    def __init__(self) -> None:
        # Underlying insightface.app.FaceAnalysis — typed as Any because
        # insightface is not imported at module load time.
        self._app: Any = None
        self._loaded: bool = False
        self._load_error: str | None = None
        self._load_duration_ms: int | None = None
        self._memory_delta_bytes: int | None = None

    # ── Singleton management ───────────────────────────────────────────

    @classmethod
    def instance(cls) -> "FaceModel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        """Test helper. Drops the singleton so the next instance()
        call returns a fresh object."""
        cls._instance = None

    # ── Load ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Idempotently load the InsightFace buffalo_l pack.

        On success: sets ``_loaded = True``, records load duration and
        memory delta.

        On failure: sets ``_load_error`` to a human-readable message and
        leaves ``_loaded = False``. Does NOT raise — callers must check
        ``.loaded`` before calling ``detect_and_embed``.

        The heavy ``insightface`` import happens inside this method so
        that the enclosing module is importable even when the deps are
        not installed (e.g. in unit tests that mock the singleton).
        """
        if self._loaded:
            return

        started = time.perf_counter()
        rss_before = _current_rss_bytes()

        try:
            # Lazy import. Failure here (ModuleNotFoundError, ImportError,
            # dynamic library load failure, etc.) is reported as a normal
            # load error — no crash.
            from insightface.app import FaceAnalysis  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001 — broad by design (see docstring)
            self._load_error = (
                f"insightface import failed: {type(exc).__name__}: {exc}"
            )
            logger.warning(
                "face_model.load_failed",
                reason="import_error",
                error_type=type(exc).__name__,
            )
            return

        try:
            app = FaceAnalysis(
                name=MODEL_PACK_NAME,
                root=settings.INSIGHTFACE_MODEL_DIR,
                providers=PROVIDERS,
            )
            app.prepare(ctx_id=CTX_ID, det_size=DETECTION_SIZE)
        except Exception as exc:  # noqa: BLE001
            self._load_error = (
                f"FaceAnalysis init failed: {type(exc).__name__}: {exc}"
            )
            logger.warning(
                "face_model.load_failed",
                reason="init_error",
                error_type=type(exc).__name__,
                model_dir=settings.INSIGHTFACE_MODEL_DIR,
            )
            return

        self._app = app
        self._loaded = True
        self._load_duration_ms = int((time.perf_counter() - started) * 1000)
        self._memory_delta_bytes = _current_rss_bytes() - rss_before

        # NOTE: no PII in this log — only versions, timing, memory delta
        logger.info(
            "face_model.loaded",
            detector_version=DETECTOR_VERSION,
            recognizer_version=RECOGNIZER_VERSION,
            load_duration_ms=self._load_duration_ms,
            memory_delta_mb=round(self._memory_delta_bytes / (1024 * 1024), 1),
            model_dir=settings.INSIGHTFACE_MODEL_DIR,
        )

    # ── Status ──────────────────────────────────────────────────────────

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def detector_version(self) -> str:
        return DETECTOR_VERSION

    @property
    def recognizer_version(self) -> str:
        return RECOGNIZER_VERSION

    def status_dict(self) -> dict[str, Any]:
        """Serializable snapshot for the /health endpoint."""
        return {
            "loaded": self._loaded,
            "load_error": self._load_error,
            "detector_version": DETECTOR_VERSION,
            "recognizer_version": RECOGNIZER_VERSION,
            "load_duration_ms": self._load_duration_ms,
            "memory_delta_mb": (
                round(self._memory_delta_bytes / (1024 * 1024), 1)
                if self._memory_delta_bytes is not None
                else None
            ),
        }

    # ── Inference ───────────────────────────────────────────────────────

    def detect_and_embed(
        self,
        image_bytes: bytes,
        *,
        photo_asset_id: UUID | None = None,
    ) -> list[FaceResult]:
        """Decode, detect, embed. Returns one ``FaceResult`` per detected face.

        Args:
            image_bytes: Raw bytes of an image file (JPEG, PNG, etc).
            photo_asset_id: Optional UUID used for log correlation. Never
                echoes the filename or image content.

        Raises:
            FaceModelNotLoadedError: if called before a successful load.
            FaceModelInvalidImageError: if OpenCV cannot decode the bytes.
        """
        if not self._loaded or self._app is None:
            raise FaceModelNotLoadedError(
                error_code="FACE_MODEL_NOT_LOADED",
                message=(
                    "Face detection model is not loaded. Call "
                    "FaceModel.instance().load() first."
                ),
            )

        # Pull cv2 + numpy from the module cache (populated lazily on
        # first real call, or pre-populated by tests with fakes).
        _ensure_cv2_numpy()
        cv2 = _cv2  # local alias for speed + test readability
        np = _np

        started = time.perf_counter()

        # Decode into a BGR ndarray. cv2.imdecode returns None on
        # unsupported or corrupt input.
        img = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if img is None:
            raise FaceModelInvalidImageError(
                error_code="FACE_MODEL_INVALID_IMAGE",
                message="OpenCV could not decode the provided image bytes.",
            )

        # insightface returns a list of Face objects with .bbox, .det_score,
        # .normed_embedding (all numpy arrays).
        faces = self._app.get(img)

        results: list[FaceResult] = []
        for face in faces:
            bbox_arr = face.bbox  # [x1, y1, x2, y2]
            x1, y1, x2, y2 = (float(v) for v in bbox_arr)
            embedding = face.normed_embedding
            if embedding is None:
                # Skip faces with no recognizer output — should be rare
                continue
            emb_list = [float(v) for v in embedding]
            if len(emb_list) != EMBEDDING_DIM:
                logger.warning(
                    "face_model.unexpected_embedding_dim",
                    expected=EMBEDDING_DIM,
                    actual=len(emb_list),
                )
                continue
            results.append(
                FaceResult(
                    bbox={
                        "x": x1,
                        "y": y1,
                        "w": x2 - x1,
                        "h": y2 - y1,
                    },
                    detection_score=float(face.det_score),
                    embedding=emb_list,
                )
            )

        duration_ms = int((time.perf_counter() - started) * 1000)

        # PII-safe log: only counts, timing, and correlation id
        logger.info(
            "face_model.detected",
            photo_asset_id=str(photo_asset_id) if photo_asset_id else None,
            face_count=len(results),
            duration_ms=duration_ms,
        )

        return results


# ── /health integration helper ─────────────────────────────────────────────


def face_model_status() -> dict[str, Any]:
    """Snapshot for /health. Safe to call before load(). Never raises."""
    return FaceModel.instance().status_dict()


