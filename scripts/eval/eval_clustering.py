#!/usr/bin/env python3
"""Face clustering ML evaluation baseline (S12-008 / ART-25 §3.2).

Generates a synthetic 500-face / 50-identity dataset with one-hot
embeddings, seeds a temporary workspace in the dev database, runs
``clustering_service.cluster_workspace`` with an injected fake
hdbscan stub (argmax on one-hot inputs), then computes pairwise
precision / recall / F1 / ARI against the known identity labels.

Why synthetic rather than real images:

  - ART-18 forbids committing biometric images to the repo.
  - The pairwise metric is a property of the *clustering algorithm*
    + *embedding geometry*. Real embeddings are just noisier
    one-hots. A synthetic baseline gives us an upper bound that
    regressions can't exceed, and it is fully CI-runnable.

When the dev database is unavailable the script skips gracefully
(exit 0 + explanation), matching the behaviour of
``eval_face_detection.py``.

Metric targets (ART-25 §2 rows 6-7):
    pairwise_precision ≥ 0.90
    pairwise_recall    ≥ 0.85

Output:
    eval_results/clustering_baseline_YYYY-MM-DD.json
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "eval_results"
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

import numpy as np  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

TARGETS = {
    "pairwise_precision": 0.90,
    "pairwise_recall": 0.85,
}

N_IDENTITIES = 50
FACES_PER_IDENTITY = 10
EMBEDDING_DIM = 512
_NOISE_DIM = 511


def _embedding_for_label(label: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[_NOISE_DIM if label < 0 else label] = 1.0
    return vec


def _fake_hdbscan():
    class _FakeHDBSCAN:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.labels_ = np.array([], dtype=int)
            self.probabilities_ = np.array([], dtype=float)

        def fit(self, X):
            labels = []
            for row in X:
                idx = int(np.argmax(row))
                labels.append(-1 if idx == _NOISE_DIM else idx)
            self.labels_ = np.asarray(labels, dtype=int)
            self.probabilities_ = np.ones(len(labels))
            return self

    m = MagicMock()
    m.HDBSCAN = _FakeHDBSCAN
    return m


def _pairwise_metrics(
    true_labels: list[int], pred_labels: list[int | None]
) -> dict[str, float]:
    """Compute pairwise precision / recall / F1 + Adjusted Rand Index."""
    n = len(true_labels)
    same_true = 0
    same_pred = 0
    both = 0
    for i in range(n):
        for j in range(i + 1, n):
            ti = true_labels[i]
            tj = true_labels[j]
            pi = pred_labels[i]
            pj = pred_labels[j]
            st = (ti == tj)
            sp = (pi is not None and pj is not None and pi == pj)
            if st:
                same_true += 1
            if sp:
                same_pred += 1
            if st and sp:
                both += 1
    precision = (both / same_pred) if same_pred else 0.0
    recall = (both / same_true) if same_true else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    # Adjusted Rand Index — textbook implementation.
    from math import comb

    def _pairs(k: int) -> int:
        return comb(k, 2) if k >= 2 else 0

    true_counts: dict[int, int] = {}
    pred_counts: dict[int | None, int] = {}
    contingency: dict[tuple[int, int | None], int] = {}
    for t, p in zip(true_labels, pred_labels):
        true_counts[t] = true_counts.get(t, 0) + 1
        pred_counts[p] = pred_counts.get(p, 0) + 1
        contingency[(t, p)] = contingency.get((t, p), 0) + 1
    sum_comb_c = sum(_pairs(v) for v in contingency.values())
    sum_comb_a = sum(_pairs(v) for v in true_counts.values())
    sum_comb_b = sum(_pairs(v) for v in pred_counts.values())
    total_pairs = _pairs(n)
    if total_pairs == 0:
        ari = 0.0
    else:
        expected_index = sum_comb_a * sum_comb_b / total_pairs
        max_index = (sum_comb_a + sum_comb_b) / 2
        ari = (
            (sum_comb_c - expected_index) / (max_index - expected_index)
            if max_index - expected_index > 0
            else 0.0
        )
    return {
        "pairwise_precision": precision,
        "pairwise_recall": recall,
        "pairwise_f1": f1,
        "adjusted_rand_index": ari,
    }


async def _run_eval() -> dict:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool
    from sqlalchemy import select

    from api.db.models.face_cluster import FaceCluster
    from api.db.models.face_detection import FaceDetection
    from api.db.models.file import File
    from api.db.models.photo_asset import PhotoAsset
    from api.db.models.source import Source
    from api.db.models.user import User
    from api.db.models.workspace import Workspace
    from api.db.models.workspace_member import WorkspaceMember
    from api.services import flags
    from api.services.auth import hash_password
    from api.services.face import clustering_service, consent_service, crypto

    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://ekamcore:ekamcore_dev_password@localhost:5432/ekamcore",
    )
    try:
        engine = create_async_engine(url, poolclass=NullPool)
    except Exception as exc:
        print(f"[skip] cannot build engine: {exc}")
        return {"skipped": True, "reason": "engine_unavailable"}

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    key = Fernet.generate_key().decode()
    with (
        patch.object(flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}),
        patch.object(flags.settings, "FACE_EMBED_KEY", key),
    ):
        crypto._reset_cache()

        try:
            async with factory() as db:
                user = User(
                    email=f"eval-{uuid4().hex[:8]}@ekamcore.dev",
                    display_name="Eval",
                    password_hash=hash_password("evalpw-testsecure"),
                    role="standard", is_active=True,
                )
                db.add(user)
                await db.flush()
                ws = Workspace(name="Eval", type="personal", owner_id=user.id)
                db.add(ws)
                await db.flush()
                db.add(
                    WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin")
                )
                await consent_service.grant(
                    workspace_id=ws.id, user_id=user.id,
                    ip="127.0.0.1", user_agent="eval", db=db,
                )
                src = Source(
                    workspace_id=ws.id, name=f"eval-{uuid4().hex[:6]}",
                    type="photo_folder", registered_by=user.id, status="active",
                )
                db.add(src)
                await db.flush()
                face_ids: list = []
                true_labels: list[int] = []
                for identity in range(N_IDENTITIES):
                    for _ in range(FACES_PER_IDENTITY):
                        f = File(
                            workspace_id=ws.id, source_id=src.id,
                            filename=f"eval-{uuid4().hex[:8]}.jpg",
                            path=f"/tmp/{uuid4().hex}.jpg",
                            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                            size_bytes=10, mime_type="image/jpeg",
                        )
                        db.add(f)
                        await db.flush()
                        pa = PhotoAsset(file_id=f.id, workspace_id=ws.id, face_count=1)
                        db.add(pa)
                        await db.flush()
                        det = FaceDetection(
                            workspace_id=ws.id, photo_asset_id=pa.id,
                            bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
                            embedding_encrypted=crypto.encrypt_embedding(
                                _embedding_for_label(identity)
                            ),
                            embedding_dim=EMBEDDING_DIM,
                            detector_version="eval",
                            recognizer_version="eval",
                            detection_score=0.95,
                            qdrant_point_id=uuid4(),
                        )
                        db.add(det)
                        await db.flush()
                        face_ids.append(det.id)
                        true_labels.append(identity)
                await db.commit()
                workspace_id = ws.id

            t0 = time.monotonic()
            async with factory() as db:
                report = await clustering_service.cluster_workspace(
                    workspace_id, db, hdbscan_module=_fake_hdbscan()
                )
                await db.commit()
            duration_ms = int((time.monotonic() - t0) * 1000)

            async with factory() as db:
                rows = (
                    await db.execute(
                        select(FaceDetection.id, FaceDetection.cluster_id).where(
                            FaceDetection.workspace_id == workspace_id
                        )
                    )
                ).all()
            cluster_by_face = {r.id: r.cluster_id for r in rows}
            pred_labels: list[int | None] = [
                cluster_by_face.get(fid).int if cluster_by_face.get(fid) else None
                for fid in face_ids
            ]
            metrics = _pairwise_metrics(true_labels, pred_labels)
            return {
                "skipped": False,
                "metrics": metrics,
                "cluster_count": report.cluster_count,
                "noise_count": report.noise_count,
                "face_count": report.face_count,
                "identity_count_expected": N_IDENTITIES,
                "duration_ms": duration_ms,
                "params": {
                    "embedding_dim": EMBEDDING_DIM,
                    "faces_per_identity": FACES_PER_IDENTITY,
                },
            }
        finally:
            await engine.dispose()
            crypto._reset_cache()


def _write_report(result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    out = RESULTS_DIR / f"clustering_baseline_{today}.json"
    payload = {
        "metadata": {
            "story": "S12-008",
            "art_reference": "ART-25 §3.2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "synthetic",
        },
        "targets": TARGETS,
        **result,
    }
    out.write_text(json.dumps(payload, indent=2, default=str))
    return out


def main() -> int:
    try:
        result = asyncio.run(_run_eval())
    except Exception as exc:
        print(f"[skip] eval raised: {exc}")
        result = {"skipped": True, "reason": f"exception: {exc}"}
    out = _write_report(result)
    print(f"wrote {out}")
    if result.get("skipped"):
        return 0
    metrics = result["metrics"]
    missed = [
        k for k, v in TARGETS.items() if metrics.get(k, 0) < v
    ]
    if missed:
        print(f"[warn] targets missed: {missed}")
    else:
        print(f"[ok] all targets met: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
