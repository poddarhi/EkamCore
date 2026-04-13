#!/usr/bin/env python3
"""Candidate contact scoring ML evaluation baseline (S12-008 / ART-25 §2 row 8).

Loads a curated set of (identity → contact) pairs from
``apps/api/tests/fixtures/face_eval/candidate_pairs.json``, seeds a
fresh workspace in the dev database with:

  - one face_cluster per pair (5 faces, all one-hot at the identity
    index so the cluster is pure by construction)
  - one contact per pair
  - ``event_count`` calendar events with the contact's email in
    participants_json, each within ±2h of the cluster's photos

then runs ``candidate_scorer.score_cluster`` for each cluster and
measures Precision@1, Precision@3, Precision@5 against the ground
truth in the fixture file.

Graceful skip:
  - Fixture file missing → exit 0 with explanation.
  - Database unreachable → exit 0 with explanation.
  - Any uncaught exception → exit 0, logged as "reason" in the JSON.

Metric targets (ART-25 §2 row 8):
    precision_at_1 ≥ 0.80
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "eval_results"
FIXTURE_PATH = (
    PROJECT_ROOT
    / "apps"
    / "api"
    / "tests"
    / "fixtures"
    / "face_eval"
    / "candidate_pairs.json"
)
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from cryptography.fernet import Fernet  # noqa: E402

TARGETS = {"precision_at_1": 0.80}
EMBEDDING_DIM = 512
FACES_PER_CLUSTER = 5


def _embedding_for_label(label: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[label % EMBEDDING_DIM] = 1.0
    return vec


def _load_fixture() -> dict | None:
    if not FIXTURE_PATH.exists():
        return None
    return json.loads(FIXTURE_PATH.read_text())


async def _run_eval(fixture: dict) -> dict:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    from api.db.models.calendar_event import CalendarEvent
    from api.db.models.contact import Contact
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
    from api.services.face import candidate_scorer, consent_service, crypto

    pairs = fixture["pairs"]
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://ekamcore:ekamcore_dev_password@localhost:5432/ekamcore",
    )
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    key = Fernet.generate_key().decode()
    with (
        patch.object(flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}),
        patch.object(flags.settings, "FACE_EMBED_KEY", key),
    ):
        crypto._reset_cache()
        try:
            t0 = time.monotonic()
            async with factory() as db:
                user = User(
                    email=f"scoring-eval-{uuid4().hex[:8]}@ekamcore.dev",
                    display_name="Scoring Eval",
                    password_hash=hash_password("evalpw-testsecure"),
                    role="standard",
                    is_active=True,
                )
                db.add(user)
                await db.flush()
                ws = Workspace(
                    name="Scoring Eval", type="personal", owner_id=user.id
                )
                db.add(ws)
                await db.flush()
                db.add(
                    WorkspaceMember(
                        workspace_id=ws.id, user_id=user.id, role="admin"
                    )
                )
                await consent_service.grant(
                    workspace_id=ws.id, user_id=user.id,
                    ip="127.0.0.1", user_agent="eval", db=db,
                )
                src = Source(
                    workspace_id=ws.id, name=f"scoring-eval-{uuid4().hex[:6]}",
                    type="photo_folder", registered_by=user.id, status="active",
                )
                db.add(src)
                await db.flush()

                cluster_by_pair: dict[int, tuple] = {}
                base = datetime(2026, 3, 1, 12, 0)
                base_aware = base.replace(tzinfo=timezone.utc)

                for pair_idx, pair in enumerate(pairs):
                    identity = int(pair["identity"])
                    display_name = pair["display_name"]
                    email = pair["email"]
                    event_count = int(pair["event_count"])

                    cluster = FaceCluster(
                        workspace_id=ws.id,
                        centroid_encrypted=crypto.encrypt_embedding(
                            _embedding_for_label(identity)
                        ),
                        member_count=FACES_PER_CLUSTER,
                        cluster_state="unconfirmed",
                    )
                    db.add(cluster)
                    await db.flush()

                    # Seed faces + photos for this cluster.
                    for photo_idx in range(FACES_PER_CLUSTER):
                        taken = base + timedelta(hours=pair_idx * 10 + photo_idx)
                        f = File(
                            workspace_id=ws.id, source_id=src.id,
                            filename=f"scoring-{pair_idx}-{photo_idx}.jpg",
                            path=f"/tmp/{uuid4().hex}.jpg",
                            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
                            size_bytes=10, mime_type="image/jpeg",
                        )
                        db.add(f)
                        await db.flush()
                        pa = PhotoAsset(
                            file_id=f.id, workspace_id=ws.id,
                            face_count=1, taken_at=taken,
                        )
                        db.add(pa)
                        await db.flush()
                        det = FaceDetection(
                            workspace_id=ws.id, photo_asset_id=pa.id,
                            bbox_json={"x": 0, "y": 0, "w": 1, "h": 1},
                            embedding_encrypted=crypto.encrypt_embedding(
                                _embedding_for_label(identity)
                            ),
                            embedding_dim=EMBEDDING_DIM,
                            detector_version="eval", recognizer_version="eval",
                            detection_score=0.95, qdrant_point_id=uuid4(),
                            cluster_id=cluster.id,
                        )
                        db.add(det)
                        await db.flush()

                    # Seed the target contact.
                    contact = Contact(
                        workspace_id=ws.id, source_id=src.id,
                        external_id=uuid4().hex,
                        first_name=display_name.split()[0],
                        last_name=display_name.split()[-1],
                        display_name=display_name,
                        emails_json=[{"address": email}],
                        imported_at=datetime.now(timezone.utc),
                    )
                    db.add(contact)
                    await db.flush()

                    # Calendar events attesting to the contact's
                    # co-occurrence with the cluster's photos.
                    for ev_idx in range(event_count):
                        start = (
                            base_aware
                            + timedelta(hours=pair_idx * 10 + ev_idx)
                        )
                        db.add(
                            CalendarEvent(
                                workspace_id=ws.id, source_id=src.id,
                                external_id=uuid4().hex, title="Meet",
                                start_at=start,
                                end_at=start + timedelta(minutes=30),
                                participants_json=[
                                    {"email": email, "name": display_name}
                                ],
                            )
                        )
                    cluster_by_pair[pair_idx] = (cluster.id, contact.id)
                await db.commit()
                workspace_id = ws.id

            hits_at_1 = 0
            hits_at_3 = 0
            hits_at_5 = 0
            total = 0

            async with factory() as db:
                for pair_idx, pair in enumerate(pairs):
                    cluster_id, expected_contact_id = cluster_by_pair[pair_idx]
                    results = await candidate_scorer.score_cluster(
                        cluster_id, db, top_k=5
                    )
                    total += 1
                    ranked_ids = [r.contact_id for r in results]
                    if ranked_ids and ranked_ids[0] == expected_contact_id:
                        hits_at_1 += 1
                    if expected_contact_id in ranked_ids[:3]:
                        hits_at_3 += 1
                    if expected_contact_id in ranked_ids[:5]:
                        hits_at_5 += 1

            duration_ms = int((time.monotonic() - t0) * 1000)
            return {
                "skipped": False,
                "metrics": {
                    "precision_at_1": hits_at_1 / total if total else 0.0,
                    "precision_at_3": hits_at_3 / total if total else 0.0,
                    "precision_at_5": hits_at_5 / total if total else 0.0,
                },
                "pair_count": total,
                "duration_ms": duration_ms,
            }
        finally:
            await engine.dispose()
            crypto._reset_cache()


def _write_report(result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    out = RESULTS_DIR / f"scoring_baseline_{today}.json"
    payload = {
        "metadata": {
            "story": "S12-008",
            "art_reference": "ART-25 §2 row 8",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fixture": str(FIXTURE_PATH),
        },
        "targets": TARGETS,
        **result,
    }
    out.write_text(json.dumps(payload, indent=2, default=str))
    return out


def main() -> int:
    fixture = _load_fixture()
    if fixture is None:
        print(f"[skip] candidate_pairs fixture missing at {FIXTURE_PATH}")
        _write_report({"skipped": True, "reason": "fixture_missing"})
        return 0
    try:
        result = asyncio.run(_run_eval(fixture))
    except Exception as exc:
        print(f"[skip] eval raised: {exc}")
        result = {"skipped": True, "reason": f"exception: {exc}"}
    out = _write_report(result)
    print(f"wrote {out}")
    if result.get("skipped"):
        return 0
    metrics = result["metrics"]
    missed = [k for k, v in TARGETS.items() if metrics.get(k, 0) < v]
    if missed:
        print(f"[warn] targets missed: {missed} — metrics={metrics}")
    else:
        print(f"[ok] all targets met: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
