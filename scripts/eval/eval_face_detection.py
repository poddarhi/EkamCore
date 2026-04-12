#!/usr/bin/env python3
"""Face detection ML evaluation baseline (S11-009 / ART-25 §3.2).

Runs the FaceModel.detect_and_embed pipeline over a local calibration
dataset and writes a JSON baseline report to ``eval_results/``. Serves
as the reference for Sprint 12 clustering eval — any regression in
detection rate, confidence, or latency should be caught by diffing a
new run against this baseline.

Usage:
    python scripts/eval/eval_face_detection.py
    python scripts/eval/eval_face_detection.py \\
        --fixtures /path/to/face_eval --limit 100

Environment:
    INSIGHTFACE_MODEL_DIR  — required; path to the buffalo_l pack
    (the same env var used by the workers container per S11-005)

Graceful skip conditions:
    1. ``insightface`` Python package not installed
    2. INSIGHTFACE_MODEL_DIR not set or not a directory
    3. Fixture directory missing or empty

When any skip condition holds the script prints a clear explanation
and exits 0 — this is a deliberate design so that running ``make
eval-face`` in CI or on a dev machine never fails just because the
dataset hasn't been placed locally. The calibration dataset is NOT
committed (it contains biometric data per ART-18); the owner places
it manually once per workstation. See
``apps/api/tests/fixtures/face_eval/README.md`` for the layout spec.

Metric targets (ART-25 §3.2):
    detection_rate  ≥ 95%       — fraction of images with ≥1 face detected
    mean_score      ≥ 0.85      — average detection_score across all faces
    latency_p50_ms  < 200       — Mac mini M4 Pro
    latency_p95_ms  < 400

Output:
    eval_results/face_detection_baseline_YYYY-MM-DD.json
    eval_results/face_detection_summary.md  (appended on each run)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Project paths ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "eval_results"
DEFAULT_FIXTURES_DIR = (
    PROJECT_ROOT / "apps" / "api" / "tests" / "fixtures" / "face_eval"
)

# Add api package to path so we can import FaceModel and friends.
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

# ── Targets ───────────────────────────────────────────────────────────────────

TARGETS: dict[str, float] = {
    "detection_rate": 0.95,
    "mean_score": 0.85,
    "latency_p50_ms": 200.0,
    "latency_p95_ms": 400.0,
}

# Accepted image extensions (match the ingestion pipeline's _PHOTO_SUFFIXES)
IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tiff",
    ".tif",
    ".heic",
    ".heif",
}


# ── Skip helpers ──────────────────────────────────────────────────────────────


def _skip(reason: str, *, exit_code: int = 0) -> None:
    """Print a skip message in a consistent format and exit.

    Exit code 0 by default: "not able to run" is never a failure in CI,
    only "ran and regressed" is.
    """
    print(
        f"[eval_face_detection] SKIP: {reason}\n"
        "See apps/api/tests/fixtures/face_eval/README.md for setup."
    )
    sys.exit(exit_code)


def _check_prereqs(fixtures_dir: Path) -> None:
    try:
        import insightface  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        _skip(f"insightface not importable: {type(exc).__name__}: {exc}")

    model_dir = os.environ.get("INSIGHTFACE_MODEL_DIR", "")
    if not model_dir:
        _skip("INSIGHTFACE_MODEL_DIR env var not set")
    if not Path(model_dir).is_dir():
        _skip(f"INSIGHTFACE_MODEL_DIR points to missing dir: {model_dir!r}")

    if not fixtures_dir.is_dir():
        _skip(f"fixtures directory missing: {fixtures_dir}")

    images = list(_iter_images(fixtures_dir))
    if not images:
        _skip(f"no image files under {fixtures_dir}")


def _iter_images(fixtures_dir: Path) -> list[Path]:
    """Return a sorted list of image files under ``fixtures_dir`` (recursive)."""
    return sorted(
        p
        for p in fixtures_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


# ── Percentile helper (dependency-free) ───────────────────────────────────────


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    values = sorted(data)
    k = (len(values) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return float(values[f])
    return float(values[f] + (values[c] - values[f]) * (k - f))


# ── Per-image run ─────────────────────────────────────────────────────────────


def _run_one_image(path: Path, face_model: Any) -> dict[str, Any]:
    """Run a single image through detect_and_embed and return a case dict.

    Never raises: decode failures / zero-face cases are recorded as
    ``ok: false`` so the aggregate row still includes them in the
    denominator of detection_rate.
    """
    try:
        image_bytes = path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        return {
            "path": str(path.name),
            "ok": False,
            "error": f"read_failed:{type(exc).__name__}",
            "face_count": 0,
            "latency_ms": 0.0,
            "top_score": 0.0,
        }

    started = time.perf_counter()
    try:
        faces = face_model.detect_and_embed(image_bytes)
    except Exception as exc:  # noqa: BLE001
        return {
            "path": str(path.name),
            "ok": False,
            "error": f"detect_failed:{type(exc).__name__}",
            "face_count": 0,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "top_score": 0.0,
        }
    latency_ms = (time.perf_counter() - started) * 1000.0

    top_score = (
        max((float(f.detection_score) for f in faces), default=0.0)
        if faces
        else 0.0
    )
    return {
        # path is intentionally reduced to filename-only; the parent
        # directory is often the identity label and we don't want to
        # leak full filesystem paths into a tracked artifact.
        "path": str(path.name),
        "ok": bool(faces),
        "error": None,
        "face_count": len(faces),
        "latency_ms": round(latency_ms, 2),
        "top_score": round(top_score, 4),
    }


# ── Aggregate + report ────────────────────────────────────────────────────────


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    ok_count = sum(1 for c in cases if c["ok"])
    latencies = [c["latency_ms"] for c in cases if c["ok"]]
    scores = [c["top_score"] for c in cases if c["ok"] and c["face_count"] > 0]

    return {
        "image_count": total,
        "detection_rate": round(ok_count / total, 4) if total else 0.0,
        "mean_score": round(statistics.fmean(scores), 4) if scores else 0.0,
        "latency_p50_ms": round(_percentile(latencies, 50), 2),
        "latency_p95_ms": round(_percentile(latencies, 95), 2),
        "latency_mean_ms": (
            round(statistics.fmean(latencies), 2) if latencies else 0.0
        ),
    }


def _pass_fail(metrics: dict[str, Any]) -> dict[str, bool]:
    return {
        "detection_rate": metrics["detection_rate"] >= TARGETS["detection_rate"],
        "mean_score": metrics["mean_score"] >= TARGETS["mean_score"],
        "latency_p50_ms": metrics["latency_p50_ms"] < TARGETS["latency_p50_ms"],
        "latency_p95_ms": metrics["latency_p95_ms"] < TARGETS["latency_p95_ms"],
    }


def _write_report(metrics: dict[str, Any], cases: list[dict[str, Any]]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = RESULTS_DIR / f"face_detection_baseline_{date_str}.json"

    passed = _pass_fail(metrics)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "story": "S11-009",
        "spec_reference": "ART-25 §3.2",
        "targets": TARGETS,
        "metrics": metrics,
        "passed": passed,
        "overall_pass": all(passed.values()),
        "cases": cases,
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return out_path


def _print_summary(
    metrics: dict[str, Any], passed: dict[str, bool], out_path: Path
) -> None:
    print("\n[eval_face_detection] Face detection baseline")
    print(f"  result file        : {out_path}")
    print(f"  images processed   : {metrics['image_count']}")
    print(
        f"  detection_rate     : {metrics['detection_rate']:.2%} "
        f"(target ≥ {TARGETS['detection_rate']:.2%}) "
        f"{'PASS' if passed['detection_rate'] else 'FAIL'}"
    )
    print(
        f"  mean_score         : {metrics['mean_score']:.4f} "
        f"(target ≥ {TARGETS['mean_score']:.2f}) "
        f"{'PASS' if passed['mean_score'] else 'FAIL'}"
    )
    print(
        f"  latency_p50_ms     : {metrics['latency_p50_ms']:.1f} "
        f"(target < {TARGETS['latency_p50_ms']:.0f}) "
        f"{'PASS' if passed['latency_p50_ms'] else 'FAIL'}"
    )
    print(
        f"  latency_p95_ms     : {metrics['latency_p95_ms']:.1f} "
        f"(target < {TARGETS['latency_p95_ms']:.0f}) "
        f"{'PASS' if passed['latency_p95_ms'] else 'FAIL'}"
    )
    print(
        f"  overall            : "
        f"{'PASS' if all(passed.values()) else 'FAIL'}"
    )


# ── Entry point ───────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help=(
            "Directory containing calibration images (recursive). "
            f"Default: {DEFAULT_FIXTURES_DIR}"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N images (useful for smoke runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    fixtures_dir = args.fixtures.resolve()

    _check_prereqs(fixtures_dir)

    # Imports are deferred until after _check_prereqs so a missing
    # insightface doesn't crash the script at parse time.
    from api.services.face.face_model import FaceModel

    face_model = FaceModel.instance()
    face_model.load()
    if not face_model.loaded:
        _skip(f"FaceModel failed to load: {face_model.load_error}")

    images = _iter_images(fixtures_dir)
    if args.limit is not None:
        images = images[: args.limit]
    print(
        f"[eval_face_detection] Running on {len(images)} images from {fixtures_dir}"
    )

    cases = [_run_one_image(p, face_model) for p in images]
    metrics = _aggregate(cases)
    passed = _pass_fail(metrics)
    out_path = _write_report(metrics, cases)
    _print_summary(metrics, passed, out_path)

    # Exit 0 even on regression — this is a baseline script, not a
    # pass/fail gate. Diffing against previous baselines is the job
    # of compare_versions.py or a future dedicated diff tool.
    return 0


if __name__ == "__main__":
    sys.exit(main())
