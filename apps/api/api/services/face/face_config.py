"""Constants for the face pipeline (S11-005).

Centralized so both the face_model module and any worker wiring read
the same values. Split from face_model.py to keep that module focused
on behavior and to make the constants trivially importable in tests
without triggering the lazy `insightface` import.
"""

from __future__ import annotations

# InsightFace model pack name. buffalo_l contains SCRFD-10g_bnkps
# (detector + landmarks) and ArcFace-R100/w600k_r50 (recognizer), plus
# 2d106det, 1k3d68, and genderage heads. See ART-15 §4 for why this
# specific pack is the Phase 3 anchor.
MODEL_PACK_NAME: str = "buffalo_l"

# Version strings embedded in face_detections rows so we can tell which
# weights produced which embedding when rolling forward or re-indexing.
DETECTOR_VERSION: str = "scrfd_10g_bnkps@buffalo_l"
RECOGNIZER_VERSION: str = "arcface_r100@buffalo_l"

# Detection target size. SCRFD supports multiple inputs; 640x640 is the
# buffalo_l default and the one ART-15 §4 mandates for reproducibility.
DETECTION_SIZE: tuple[int, int] = (640, 640)

# ctx_id = -1 forces CPU. GPU execution is explicitly out of scope for
# v1.0 (Apple Silicon unified memory profile and offline-first
# guarantees both rule out CUDA).
CTX_ID: int = -1

# ONNX Runtime providers. CPUExecutionProvider is always present and
# matches CTX_ID = -1. CoreMLExecutionProvider could be added later if
# we bundle a second wheel of onnxruntime-silicon; out of S11-005 scope.
PROVIDERS: list[str] = ["CPUExecutionProvider"]

# Expected embedding dimension. ArcFace-R100 in buffalo_l produces 512.
EMBEDDING_DIM: int = 512
