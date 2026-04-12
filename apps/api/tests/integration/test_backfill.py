"""Integration tests for face backfill service + endpoints (S11-007).

Two test surfaces:

  1. Service-level (TestBackfillWorker): calls _process_workspace
     directly with a mocked process_photo_for_faces so we can observe
     the worker loop deterministically without asyncio.create_task
     coordination headaches.

  2. API-level (TestBackfillEndpoints): exercises POST/GET/DELETE at
     /api/v1/settings/face-clustering/backfill via the shared client.

Note on mocking: the worker queries "photos where face_processed_at IS
NULL" in a tight loop. Our mocked process_photo_for_faces MUST stamp
face_processed_at on the PhotoAsset row, otherwise the worker sees the
same unprocessed set forever and the test loops indefinitely. The
``_stamping_process_photo`` helper handles this.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, update

from api.db.models.face_backfill_job import FaceBackfillJob
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.services import flags
from api.services.face import backfill_service, consent_service, crypto

pytestmark = pytest.mark.asyncio(loop_scope="session")

_BACKFILL_URL = "/api/v1/settings/face-clustering/backfill"


# ── Shared helpers ─────────────────────────────────────────────────────────


async def _seed_photos(db, workspace_id, *, registered_by, n: int) -> list[UUID]:
    """Create N photos (Source, File, PhotoAsset) with face_processed_at NULL."""
    src = Source(
        workspace_id=workspace_id,
        name=f"bf-src-{uuid4().hex[:6]}",
        type="photo_folder",
        registered_by=registered_by,
        status="active",
    )
    db.add(src)
    await db.flush()

    photo_ids: list[UUID] = []
    for i in range(n):
        disk = f"/tmp/ekamcore-bf-{uuid4().hex}.jpg"
        Path(disk).write_bytes(b"\xff\xd8\xff\xe0" + bytes(64))
        f = File(
            workspace_id=workspace_id,
            source_id=src.id,
            filename=f"bf-{i}.jpg",
            path=disk,
            content_hash_sha256=(uuid4().hex + uuid4().hex)[:64],
            size_bytes=68,
            mime_type="image/jpeg",
        )
        db.add(f)
        await db.flush()
        pa = PhotoAsset(
            file_id=f.id,
            workspace_id=workspace_id,
            face_count=0,
            face_processed_at=None,
        )
        db.add(pa)
        await db.flush()
        photo_ids.append(pa.id)
    await db.flush()
    return photo_ids


async def _stamping_process_photo(photo_asset_id: UUID, db, **_) -> int:
    """Drop-in replacement for process_photo_for_faces that just stamps
    face_processed_at on the PhotoAsset and increments face_count by 1.

    Critical: must actually update the row so the worker's next batch
    query no longer returns this photo. Otherwise the loop runs forever.
    """
    await db.execute(
        update(PhotoAsset)
        .where(PhotoAsset.id == photo_asset_id)
        .values(
            face_processed_at=datetime.now(timezone.utc),
            face_count=1,
        )
    )
    return 1


@pytest.fixture
def face_env():
    """Enable flag + Fernet key so face_pipeline_active returns True."""
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


# ── Service-level tests ────────────────────────────────────────────────────


class TestBackfillWorker:
    async def test_processes_all_unprocessed_photos(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            photo_ids = await _seed_photos(db, ws, registered_by=user_id, n=10)
            job = FaceBackfillJob(
                workspace_id=ws,
                total_photos=10,
                processed_photos=0,
                failed_photos=0,
                state="running",
            )
            db.add(job)
            await db.flush()
            job_id = job.id
            await db.commit()

        async with test_session_factory() as db:
            with patch(
                "api.services.face.backfill_service.process_photo_for_faces",
                side_effect=_stamping_process_photo,
            ):
                await backfill_service._process_workspace(ws, job_id, db)

        async with test_session_factory() as db:
            refreshed = (
                await db.execute(
                    select(FaceBackfillJob).where(FaceBackfillJob.id == job_id)
                )
            ).scalar_one()
            photos_done = (
                await db.execute(
                    select(PhotoAsset).where(PhotoAsset.id.in_(photo_ids))
                )
            ).scalars().all()

        assert refreshed.state == "completed"
        assert refreshed.processed_photos == 10
        assert refreshed.failed_photos == 0
        assert refreshed.finished_at is not None
        assert all(p.face_processed_at is not None for p in photos_done)

    async def test_midflight_cancel_flag_stops_worker(
        self, test_session_factory, seed_user, face_env
    ):
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            # Single batch would hold all of these, so set cancel BEFORE
            # running — worker stops before processing any photo.
            await _seed_photos(db, ws, registered_by=user_id, n=3)
            job = FaceBackfillJob(
                workspace_id=ws,
                total_photos=3,
                processed_photos=0,
                failed_photos=0,
                state="running",
            )
            db.add(job)
            await db.flush()
            job_id = job.id
            await db.commit()

        await backfill_service._set_cancel_flag(ws)

        async with test_session_factory() as db:
            with patch(
                "api.services.face.backfill_service.process_photo_for_faces",
                side_effect=_stamping_process_photo,
            ):
                await backfill_service._process_workspace(ws, job_id, db)

        async with test_session_factory() as db:
            refreshed = (
                await db.execute(
                    select(FaceBackfillJob).where(FaceBackfillJob.id == job_id)
                )
            ).scalar_one()
        assert refreshed.state == "cancelled"
        assert refreshed.processed_photos == 0

    async def test_consent_revocation_stops_worker(
        self, test_session_factory, seed_user, face_env
    ):
        """If consent is revoked between batches, the worker must stop
        and mark the job cancelled, not keep writing face rows."""
        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            await _seed_photos(db, ws, registered_by=user_id, n=2)
            job = FaceBackfillJob(
                workspace_id=ws,
                total_photos=2,
                processed_photos=0,
                failed_photos=0,
                state="running",
            )
            db.add(job)
            await db.flush()
            job_id = job.id
            await db.commit()

        # Mock face_pipeline_active to return False (simulates revocation)
        async with test_session_factory() as db:
            with (
                patch(
                    "api.services.face.backfill_service.face_pipeline_active",
                    return_value=False,
                ),
                patch(
                    "api.services.face.backfill_service.process_photo_for_faces",
                    side_effect=_stamping_process_photo,
                ),
            ):
                await backfill_service._process_workspace(ws, job_id, db)

        async with test_session_factory() as db:
            refreshed = (
                await db.execute(
                    select(FaceBackfillJob).where(FaceBackfillJob.id == job_id)
                )
            ).scalar_one()
        assert refreshed.state == "cancelled"
        assert refreshed.processed_photos == 0

    async def test_start_rejects_when_running_job_exists(
        self, test_session_factory, seed_user, face_env
    ):
        from api.errors import ConflictError

        ws = seed_user["workspace_id"]
        user_id = seed_user["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=ws, user_id=user_id,
                ip="127.0.0.1", user_agent="pytest", db=db,
            )
            await _seed_photos(db, ws, registered_by=user_id, n=1)
            # Pre-existing running job
            job = FaceBackfillJob(
                workspace_id=ws,
                total_photos=5,
                processed_photos=0,
                failed_photos=0,
                state="running",
            )
            db.add(job)
            await db.commit()

        async with test_session_factory() as db:
            with pytest.raises(ConflictError) as exc:
                await backfill_service.start_backfill(
                    workspace_id=ws,
                    db=db,
                    # no-op worker so we don't actually spawn a task
                    worker_factory=lambda: _noop_coro(),
                )
        assert exc.value.error_code == "BACKFILL_ALREADY_RUNNING"


async def _noop_coro() -> None:
    return None


# ── API-level tests ────────────────────────────────────────────────────────


def _auth_headers(tok: dict, *, with_csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    if with_csrf:
        h["X-CSRF-Token"] = tok["csrf_token"]
    return h


class TestBackfillEndpoints:
    async def test_post_requires_active_consent(self, client, auth_tokens):
        """Without consent, POST returns 403 FACE_CONSENT_REQUIRED."""
        resp = await client.post(
            _BACKFILL_URL,
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"

    async def test_post_start_returns_job_row(
        self, client, auth_tokens, face_env
    ):
        """Happy path: consent granted → POST returns 202 with the new job."""
        from api.services.face.consent_text import CURRENT_CONSENT_VERSION

        # Grant consent via the API so the full auth flow is exercised
        grant = await client.post(
            "/api/v1/settings/face-clustering/consent",
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
        )
        assert grant.status_code == 200, grant.text

        # Replace the worker coroutine with a harmless no-op so the test
        # can observe the job row without racing the background task.
        async def _fake_worker(*_a, **_k) -> None:
            return None

        with patch(
            "api.services.face.backfill_service._run_backfill_worker",
            _fake_worker,
        ):
            resp = await client.post(
                _BACKFILL_URL,
                headers=_auth_headers(auth_tokens, with_csrf=True),
                cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
            )

        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["state"] == "running"
        assert body["processed_photos"] == 0
        assert "id" in body

    async def test_duplicate_post_returns_409(
        self, client, auth_tokens, face_env
    ):
        from api.services.face.consent_text import CURRENT_CONSENT_VERSION

        await client.post(
            "/api/v1/settings/face-clustering/consent",
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
        )

        async def _fake_worker(*_a, **_k) -> None:
            return None

        from api.routers.face_backfill import _START_RATE_LIMIT_PREFIX
        from api.services.redis_client import REDIS_DB_CACHE, get_redis

        with patch(
            "api.services.face.backfill_service._run_backfill_worker",
            _fake_worker,
        ):
            first = await client.post(
                _BACKFILL_URL,
                headers=_auth_headers(auth_tokens, with_csrf=True),
                cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
            )
            assert first.status_code == 202, first.text

            # Clear the 1/hour rate-limit bucket so the second POST can
            # reach the duplicate-running check (what this test is for).
            r = get_redis(REDIS_DB_CACHE)
            await r.delete(
                f"{_START_RATE_LIMIT_PREFIX}{auth_tokens['workspace_id']}"
            )

            second = await client.post(
                _BACKFILL_URL,
                headers=_auth_headers(auth_tokens, with_csrf=True),
                cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
            )

        assert second.status_code == 409, second.text
        assert second.json()["error_code"] == "BACKFILL_ALREADY_RUNNING"

    async def test_get_returns_latest_job(
        self, client, auth_tokens, face_env
    ):
        from api.services.face.consent_text import CURRENT_CONSENT_VERSION

        await client.post(
            "/api/v1/settings/face-clustering/consent",
            json={
                "accepted": True,
                "version_acknowledged": CURRENT_CONSENT_VERSION,
            },
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
        )

        async def _fake_worker(*_a, **_k) -> None:
            return None

        with patch(
            "api.services.face.backfill_service._run_backfill_worker",
            _fake_worker,
        ):
            post_resp = await client.post(
                _BACKFILL_URL,
                headers=_auth_headers(auth_tokens, with_csrf=True),
                cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
            )
            assert post_resp.status_code == 202

        get_resp = await client.get(
            _BACKFILL_URL,
            headers=_auth_headers(auth_tokens),
        )
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body is not None
        assert body["state"] == "running"
