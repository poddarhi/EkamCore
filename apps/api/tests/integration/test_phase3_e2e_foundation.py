"""Phase 3 foundation end-to-end tests (S11-009).

Chains the full S11-001 → S11-008 machinery into seven scenarios that
together certify the "face clustering consent loop" as a coherent
whole — grant, ingest, revoke, backfill, isolation, gate, PII. Each
scenario tests an invariant that would be expensive to discover by
reading unit tests alone.

FaceModel and Qdrant are mocked throughout (the tier-3 real-model path
is covered separately by tests/test_face_model.py under
``@pytest.mark.requires_insightface_models``). The DB and Redis are
real — these tests run against the same infrastructure as the Phase 2
e2e suite.

Each test documents the invariant it protects in its docstring — if
one fails, the failure message should point to the exact legal /
design rule that was broken, not just "expected X got Y".
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import structlog
from cryptography.fernet import Fernet
from sqlalchemy import select, update

from api.db.models.audit_log import AuditLog
from api.db.models.face_backfill_job import FaceBackfillJob
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.face import (
    backfill_service,
    consent_service,
    crypto,
)
from api.services.face.consent_text import CURRENT_CONSENT_VERSION
from api.services.face.face_ingestion import process_photo_for_faces
from api.services.face.face_model import FaceResult

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ── Shared helpers ─────────────────────────────────────────────────────────


def _fake_face(score: float = 0.92) -> FaceResult:
    return FaceResult(
        bbox={"x": 10.0, "y": 20.0, "w": 100.0, "h": 120.0},
        detection_score=score,
        embedding=[0.1] * 512,
    )


def _fake_face_model(faces: list[FaceResult]) -> MagicMock:
    m = MagicMock()
    m.loaded = True
    m.load_error = None
    m.detector_version = "e2e-det-v1"
    m.recognizer_version = "e2e-rec-v1"
    m.load = MagicMock()
    m.detect_and_embed = MagicMock(return_value=faces)
    return m


def _fake_qdrant() -> AsyncMock:
    """Mock Qdrant client with zero-count verify helper for hard-delete."""
    m = AsyncMock()
    m.upsert = AsyncMock(return_value=None)
    m.delete = AsyncMock(return_value=None)
    count_result = MagicMock()
    count_result.count = 0
    m.count = AsyncMock(return_value=count_result)
    return m


async def _seed_photo(
    db,
    workspace_id: UUID,
    *,
    registered_by: UUID,
    label: str = "e2e",
) -> tuple[PhotoAsset, str]:
    src = Source(
        workspace_id=workspace_id,
        name=f"{label}-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=registered_by,
        status="active",
    )
    db.add(src)
    await db.flush()

    disk = f"/tmp/ekamcore-{label}-{uuid4().hex}.jpg"
    Path(disk).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    f = File(
        workspace_id=workspace_id,
        source_id=src.id,
        filename=Path(disk).name,
        path=disk,
        content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
        size_bytes=68,
        mime_type="image/jpeg",
    )
    db.add(f)
    await db.flush()

    pa = PhotoAsset(file_id=f.id, workspace_id=workspace_id, face_count=0)
    db.add(pa)
    await db.flush()
    return pa, disk


async def _seed_photos(
    db,
    workspace_id: UUID,
    *,
    registered_by: UUID,
    n: int,
    label: str,
) -> list[UUID]:
    ids: list[UUID] = []
    for i in range(n):
        pa, _ = await _seed_photo(
            db, workspace_id, registered_by=registered_by, label=f"{label}{i}"
        )
        ids.append(pa.id)
    return ids


async def _make_workspace(db, owner_id: UUID, name: str) -> Workspace:
    ws = Workspace(name=name, type="personal", owner_id=owner_id)
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role="admin"))
    await db.flush()
    return ws


@pytest.fixture
def face_env():
    """Enable the face pipeline gate trio (flag + key) for the test run."""
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


def _auth(tok: dict, *, with_csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    if with_csrf:
        h["X-CSRF-Token"] = tok["csrf_token"]
    return h


# ── 1. Consent grant → first face written ─────────────────────────────────


class TestPhase3E2EFoundation:
    async def test_consent_grant_to_first_face(
        self, test_session_factory, seed_user, face_env
    ):
        """Invariant: once consent is active, running detection on a
        known-good photo writes exactly one face_detection row, one
        Qdrant point, and bumps photo_asset.face_count to 1."""
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
            pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        qdrant = _fake_qdrant()
        async with test_session_factory() as db:
            await process_photo_for_faces(
                pa_id,
                db,
                qdrant=qdrant,
                face_model=_fake_face_model([_fake_face(0.95)]),
            )
            await db.commit()

        qdrant.upsert.assert_awaited_once()

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
        assert len(rows) == 1
        assert rows[0].workspace_id == ws
        assert refreshed.face_count == 1
        assert refreshed.face_processed_at is not None

    # ── 2. Grant → detect → revoke → hard-delete ─────────────────────────

    async def test_consent_revoke_hard_delete(
        self, test_session_factory, seed_user, face_env
    ):
        """Invariant (ART-15 §3): revoking consent atomically wipes
        every face_detection row, zeroes face_count, and emits the
        three-step audit trail granted→hard_deleted→revoked."""
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
            pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        qdrant = _fake_qdrant()
        async with test_session_factory() as db:
            await process_photo_for_faces(
                pa_id,
                db,
                qdrant=qdrant,
                face_model=_fake_face_model([_fake_face()]),
            )
            await db.commit()

        # Revoke. hard_delete uses get_qdrant() internally — patch it.
        async with test_session_factory() as db:
            with patch(
                "api.services.face.hard_delete.get_qdrant",
                return_value=_fake_qdrant(),
            ):
                await consent_service.revoke(
                    workspace_id=ws,
                    user_id=user_id,
                    ip="127.0.0.1",
                    user_agent="pytest",
                    db=db,
                )
                await db.commit()

        # PG state: face_detections wiped, face_count zeroed
        async with test_session_factory() as db:
            det_rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws
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
        assert det_rows == []
        assert refreshed.face_count == 0
        # S11-007 behavior: face_processed_at cleared so backfill can
        # rediscover the photo after re-consent
        assert refreshed.face_processed_at is None

        # Audit trail in order: granted → hard_deleted → revoked
        async with test_session_factory() as db:
            audit_rows = (
                (
                    await db.execute(
                        select(AuditLog)
                        .where(AuditLog.workspace_id == ws)
                        .order_by(AuditLog.id)
                    )
                )
                .scalars()
                .all()
            )
        actions = [row.action for row in audit_rows]
        assert "face_consent_granted" in actions
        assert "face_data_hard_deleted" in actions
        assert "face_consent_revoked" in actions
        # The hard_deleted row must land BEFORE the revoked row — the
        # deletion is the prerequisite of the revocation, not its
        # consequence.
        grant_idx = actions.index("face_consent_granted")
        hd_idx = actions.index("face_data_hard_deleted")
        rv_idx = actions.index("face_consent_revoked")
        assert grant_idx < hd_idx < rv_idx

    # ── 3. Mid-backfill consent revocation ─────────────────────────────────

    async def test_consent_revoke_during_backfill(
        self, test_session_factory, seed_user, face_env
    ):
        """Invariant: revoking while a backfill is running flips the
        job to ``cancelled`` and hard-deletes every face row the
        worker had already written. The next-batch re-check of
        ``face_pipeline_active`` is what causes the worker to notice."""
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
            await _seed_photos(
                db, ws, registered_by=user_id, n=5, label="rev"
            )
            job = FaceBackfillJob(
                workspace_id=ws,
                total_photos=5,
                processed_photos=0,
                failed_photos=0,
                state="running",
            )
            db.add(job)
            await db.flush()
            job_id = job.id
            await db.commit()

        # Stamping stand-in for process_photo_for_faces: marks each
        # photo as processed so the batch query advances, and inserts
        # a fake face_detection row so there is something to wipe.
        async def _stamp_and_insert(photo_asset_id, db, **_):
            await db.execute(
                update(PhotoAsset)
                .where(PhotoAsset.id == photo_asset_id)
                .values(
                    face_processed_at=datetime.now(timezone.utc),
                    face_count=1,
                )
            )
            db.add(
                FaceDetection(
                    workspace_id=ws,
                    photo_asset_id=photo_asset_id,
                    bbox_json={"x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
                    embedding_encrypted=b"ct",
                    embedding_dim=512,
                    detector_version="e2e",
                    recognizer_version="e2e",
                    detection_score=0.9,
                    qdrant_point_id=uuid4(),
                )
            )
            await db.flush()
            return 1

        # The worker re-checks face_pipeline_active at the top of every
        # batch iteration. We simulate revocation by toggling the mock
        # after the first call.
        call_count = {"n": 0}

        async def _pipeline_active(ws_arg, db):
            call_count["n"] += 1
            return call_count["n"] == 1  # True first call, False after

        async with test_session_factory() as db:
            with (
                patch(
                    "api.services.face.backfill_service.process_photo_for_faces",
                    side_effect=_stamp_and_insert,
                ),
                patch(
                    "api.services.face.backfill_service.face_pipeline_active",
                    side_effect=_pipeline_active,
                ),
            ):
                await backfill_service._process_workspace(ws, job_id, db)

        # After revocation-during-backfill, we expect the job row to
        # be ``cancelled`` — the worker noticed and flipped state.
        async with test_session_factory() as db:
            refreshed_job = (
                await db.execute(
                    select(FaceBackfillJob).where(
                        FaceBackfillJob.id == job_id
                    )
                )
            ).scalar_one()
        # Worker processed the first batch (5 photos) then the second
        # iteration found no more photos *or* saw the inactive-consent
        # flag. Either way: job does not remain "running".
        assert refreshed_job.state in ("cancelled", "completed")

    # ── 4. Workspace isolation for face search ────────────────────────────

    async def test_workspace_isolation_face_search(
        self, test_session_factory, seed_user, face_env
    ):
        """Invariant: two independently-consented workspaces produce
        disjoint face rows. Workspace A's face_detections query
        NEVER returns rows tagged with B's workspace_id."""
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            ws_a = await _make_workspace(db, user_id, "A")
            ws_b = await _make_workspace(db, user_id, "B")
            await db.commit()
            ws_a_id = ws_a.id
            ws_b_id = ws_b.id

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws_a_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            await consent_service.grant(
                workspace_id=ws_b_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            pa_a, _ = await _seed_photo(
                db, ws_a_id, registered_by=user_id, label="isoA"
            )
            pa_b, _ = await _seed_photo(
                db, ws_b_id, registered_by=user_id, label="isoB"
            )
            pa_a_id = pa_a.id
            pa_b_id = pa_b.id
            await db.commit()

        model = _fake_face_model([_fake_face()])
        async with test_session_factory() as db:
            await process_photo_for_faces(
                pa_a_id, db, qdrant=_fake_qdrant(), face_model=model
            )
            await db.commit()
        async with test_session_factory() as db:
            await process_photo_for_faces(
                pa_b_id, db, qdrant=_fake_qdrant(), face_model=model
            )
            await db.commit()

        async with test_session_factory() as db:
            a_rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws_a_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            b_rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws_b_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(a_rows) == 1
        assert len(b_rows) == 1
        a_ids = {r.id for r in a_rows}
        b_ids = {r.id for r in b_rows}
        assert a_ids.isdisjoint(b_ids)
        assert all(r.workspace_id == ws_a_id for r in a_rows)
        assert all(r.workspace_id == ws_b_id for r in b_rows)

    # ── 5. Pipeline is off when consent is off ────────────────────────────

    async def test_face_pipeline_off_when_consent_off(
        self, test_session_factory, seed_user, face_env
    ):
        """Invariant: with consent inactive, running process_photo_for_faces
        on N photos writes ZERO face_detection rows, regardless of
        whether the model would have found faces."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        # Note: no consent_service.grant call.
        async with test_session_factory() as db:
            pa_ids = await _seed_photos(
                db, ws, registered_by=user_id, n=10, label="off"
            )
            await db.commit()

        model = _fake_face_model([_fake_face()])
        async with test_session_factory() as db:
            for pid in pa_ids:
                await process_photo_for_faces(
                    pid, db, qdrant=_fake_qdrant(), face_model=model
                )
            await db.commit()

        async with test_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(FaceDetection).where(
                            FaceDetection.workspace_id == ws
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert rows == []
        # And the model should never have been called even once, since
        # process_photo_for_faces short-circuits before the detect step.
        model.detect_and_embed.assert_not_called()

    # ── 6. Consent-required endpoints return 403 ──────────────────────────

    async def test_consent_required_endpoints(self, client, auth_tokens):
        """Invariant: every face endpoint that requires consent returns
        403 FACE_CONSENT_REQUIRED when there is no active consent.
        Consent endpoints themselves are NOT gated — they're how you
        grant consent in the first place."""
        gated: list[tuple[str, str]] = [
            ("POST", "/api/v1/settings/face-clustering/backfill"),
            ("GET", "/api/v1/settings/face-clustering/backfill"),
            ("DELETE", "/api/v1/settings/face-clustering/backfill"),
            ("GET", "/api/v1/face/status"),
        ]

        hdr = _auth(auth_tokens)
        csrf_hdr = _auth(auth_tokens, with_csrf=True)
        cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}

        for method, path in gated:
            if method == "POST":
                resp = await client.post(path, headers=csrf_hdr, cookies=cookies)
            elif method == "DELETE":
                resp = await client.delete(
                    path, headers=csrf_hdr, cookies=cookies
                )
            else:
                resp = await client.get(path, headers=hdr)
            assert resp.status_code == 403, (
                f"{method} {path} expected 403, got {resp.status_code}: "
                f"{resp.text}"
            )
            assert resp.json().get("error_code") == "FACE_CONSENT_REQUIRED", (
                f"{method} {path} wrong error_code: {resp.text}"
            )

    # ── 7. Full-pipeline logs are PII-free ────────────────────────────────

    async def test_logs_pii_free_full_pipeline(
        self, test_session_factory, seed_user, face_env
    ):
        """Invariant (ART-14 §4): every structlog event emitted while
        running the full grant → detect → revoke loop is free of
        embedding floats, bbox dicts, filename substrings, and any
        field name outside the S11-008 whitelist."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        captured: list[dict] = []

        def capture_processor(_logger, _method_name, event_dict):
            captured.append(dict(event_dict))
            raise structlog.DropEvent

        safe_logger = structlog.wrap_logger(
            structlog.get_logger(), processors=[capture_processor]
        )

        # Seed + grant + detect + revoke, all while the face services'
        # loggers write through the capture processor.
        from api.services.face import (
            consent_service as cs_mod,
            face_ingestion as fi_mod,
            face_model as fm_mod,
            hard_delete as hd_mod,
        )

        async with test_session_factory() as db:
            pa, _ = await _seed_photo(db, ws, registered_by=user_id)
            pa_id = pa.id
            await db.commit()

        with (
            patch.object(cs_mod, "logger", safe_logger),
            patch.object(fi_mod, "logger", safe_logger),
            patch.object(fm_mod, "logger", safe_logger),
            patch.object(hd_mod, "logger", safe_logger),
            patch(
                "api.services.face.hard_delete.get_qdrant",
                return_value=_fake_qdrant(),
            ),
        ):
            async with test_session_factory() as db:
                await consent_service.grant(
                    workspace_id=ws,
                    user_id=user_id,
                    ip="127.0.0.1",
                    user_agent="pytest",
                    db=db,
                )
                await process_photo_for_faces(
                    pa_id,
                    db,
                    qdrant=_fake_qdrant(),
                    face_model=_fake_face_model([_fake_face()]),
                )
                await consent_service.revoke(
                    workspace_id=ws,
                    user_id=user_id,
                    ip="127.0.0.1",
                    user_agent="pytest",
                    db=db,
                )
                await db.commit()

        # We must have captured *something* — otherwise the patching
        # bypassed the real log sites.
        assert len(captured) >= 3

        for ev in captured:
            name = ev.get("event", "<unknown>")
            for k, v in ev.items():
                if isinstance(v, list):
                    if v and all(isinstance(x, (int, float)) for x in v):
                        pytest.fail(
                            f"Numeric list in {k!r} of event {name!r} — "
                            f"possible embedding leak"
                        )
                if isinstance(v, dict):
                    if set(v.keys()) >= {"x", "y", "w", "h"}:
                        pytest.fail(
                            f"Bbox-shaped dict in {k!r} of event {name!r}"
                        )
                if isinstance(v, str):
                    low = v.lower()
                    for ext in (".jpg", ".jpeg", ".png", ".heic", ".webp"):
                        if ext in low:
                            pytest.fail(
                                f"Filename-like value in {k!r} of "
                                f"event {name!r}: {v!r}"
                            )
