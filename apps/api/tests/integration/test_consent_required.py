"""Integration test: require_face_consent dependency blocks unauthorized access (S11-002).

Spins up a minimal FastAPI test endpoint under /__test/face-gated that uses
`Depends(require_face_consent)`. Verifies:
  - No consent → 403 FACE_CONSENT_REQUIRED
  - Cross-workspace request → 403 WORKSPACE_ACCESS_DENIED
  - Unauthenticated → 401
  - Consent granted → 200
  - Consent revoked → 403 again

Uses the session event loop so Redis pools created by fixtures remain valid.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends

from api.dependencies.face_consent import require_face_consent
from api.main import app as main_app
from api.services.face import consent_service
from api.services.face.consent_service import _cache_invalidate

# Integration tests share the session loop (see integration/conftest.py)
pytestmark = pytest.mark.asyncio(loop_scope="session")


# Register a test-only endpoint once at module import. Idempotent.
_test_router = APIRouter(prefix="/__test")


@_test_router.get("/face-gated")
async def _face_gated_endpoint(
    workspace_id=Depends(require_face_consent),
) -> dict:
    return {"ok": True, "workspace_id": str(workspace_id)}


if not any(
    getattr(r, "path", None) == "/__test/face-gated" for r in main_app.routes
):
    main_app.include_router(_test_router)


# ── Test cases ─────────────────────────────────────────────────────────────


class TestRequireFaceConsentDependency:
    async def test_no_consent_returns_403_face_consent_required(
        self, client, auth_tokens
    ):
        resp = await client.get(
            "/__test/face-gated",
            params={"workspace_id": str(auth_tokens["workspace_id"])},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"

    async def test_cross_workspace_returns_403_workspace_access_denied(
        self, client, auth_tokens
    ):
        other_ws = uuid4()
        resp = await client.get(
            "/__test/face-gated",
            params={"workspace_id": str(other_ws)},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "WORKSPACE_ACCESS_DENIED"

    async def test_unauthenticated_returns_401(self, client, auth_tokens):
        resp = await client.get(
            "/__test/face-gated",
            params={"workspace_id": str(auth_tokens["workspace_id"])},
        )
        assert resp.status_code == 401

    async def test_granted_consent_allows_request(
        self, client, auth_tokens, test_session_factory
    ):
        workspace_id = auth_tokens["workspace_id"]
        user_id = auth_tokens["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            await db.commit()

        # Drop the Redis consent cache so the next read sees the fresh state
        await _cache_invalidate(workspace_id)

        resp = await client.get(
            "/__test/face-gated",
            params={"workspace_id": str(workspace_id)},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["workspace_id"] == str(workspace_id)

    async def test_revoked_consent_returns_403_again(
        self, client, auth_tokens, test_session_factory
    ):
        workspace_id = auth_tokens["workspace_id"]
        user_id = auth_tokens["user_id"]

        async with test_session_factory() as db:
            await consent_service.grant(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            await db.commit()

        async with test_session_factory() as db:
            await consent_service.revoke(
                workspace_id=workspace_id,
                user_id=user_id,
                ip="127.0.0.1",
                user_agent="pytest",
                db=db,
            )
            await db.commit()

        await _cache_invalidate(workspace_id)

        resp = await client.get(
            "/__test/face-gated",
            params={"workspace_id": str(workspace_id)},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"
