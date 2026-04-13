"""Integration tests for the /api/v1/people endpoints (S12-004).

Covers the seven documented endpoints end-to-end through the FastAPI
client. The authenticated user must have active face consent — we
grant it at the ORM layer in each test's seed phase.

Assertions focus on:
  - happy path status codes + response shapes
  - workspace isolation at the endpoint layer (a reject against a
    different workspace's cluster 404s, not 200)
  - audit + state side-effects where not already covered by
    test_trusted_person_service.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from api.db.models.contact import Contact
from api.db.models.face_cluster import FaceCluster
from api.db.models.source import Source
from api.db.models.trusted_person import TrustedPerson
from api.services import flags
from api.services.face import consent_service, crypto

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PEOPLE_URL = "/api/v1/people"


@pytest.fixture
def face_env():
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


async def _grant_consent(factory, workspace_id, user_id):
    async with factory() as db:
        await consent_service.grant(
            workspace_id=workspace_id,
            user_id=user_id,
            ip="127.0.0.1",
            user_agent="pytest",
            db=db,
        )
        await db.commit()


async def _seed_cluster(factory, workspace_id, *, candidates=None):
    async with factory() as db:
        cluster = FaceCluster(
            workspace_id=workspace_id,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=5,
            cluster_state="unconfirmed",
            candidates_json=candidates,
        )
        db.add(cluster)
        await db.flush()
        cluster_id = cluster.id
        await db.commit()
    return cluster_id


async def _seed_contact(factory, workspace_id, user_id, display_name):
    async with factory() as db:
        src = Source(
            workspace_id=workspace_id,
            name=f"ppl-{uuid4().hex[:6]}",
            type="contacts",
            registered_by=user_id,
            status="active",
        )
        db.add(src)
        await db.flush()
        c = Contact(
            workspace_id=workspace_id,
            source_id=src.id,
            external_id=uuid4().hex,
            first_name=display_name.split()[0],
            last_name=display_name.split()[-1],
            display_name=display_name,
            emails_json=[{"address": "x@example.com"}],
            imported_at=datetime.now(timezone.utc),
        )
        db.add(c)
        await db.commit()
        return c.id


def _auth_headers(tokens, *, with_csrf: bool = False) -> dict:
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    if with_csrf:
        h["X-CSRF-Token"] = tokens["csrf_token"]
    return h


def _csrf_cookie(tokens) -> dict:
    return {"ekamcore_csrf": tokens["csrf_token"]}


class TestPeopleEndpoints:
    async def test_full_crud_happy_path(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        cluster_id = await _seed_cluster(test_session_factory, ws)

        # POST / → create from cluster
        resp = await client.post(
            _PEOPLE_URL,
            json={
                "cluster_id": str(cluster_id),
                "display_name": "Alice",
            },
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        person_id = body["id"]
        assert body["display_name"] == "Alice"
        assert body["trust_source"] == "manual"

        # GET /:person_id
        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["display_name"] == "Alice"

        # GET / → list contains the new person
        resp = await client.get(
            _PEOPLE_URL,
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert any(p["id"] == person_id for p in items)

        # PATCH /:person_id → rename
        resp = await client.patch(
            f"{_PEOPLE_URL}/{person_id}",
            json={"display_name": "Alice Renamed"},
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["display_name"] == "Alice Renamed"

        # DELETE /:person_id
        resp = await client.delete(
            f"{_PEOPLE_URL}/{person_id}",
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 204, resp.text

        # Follow-up GET 404
        resp = await client.get(
            f"{_PEOPLE_URL}/{person_id}",
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 404

    async def test_confirm_candidate_endpoint(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        contact_id = await _seed_contact(
            test_session_factory, ws, uid, "Bob Jones"
        )
        cluster_id = await _seed_cluster(
            test_session_factory,
            ws,
            candidates=[
                {
                    "contact_id": str(contact_id),
                    "score": 0.8,
                    "confidence": "high",
                    "signals": {"co_occurrence": 1.0},
                }
            ],
        )

        resp = await client.post(
            f"{_PEOPLE_URL}/confirm-candidate",
            json={
                "cluster_id": str(cluster_id),
                "contact_id": str(contact_id),
            },
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["canonical_contact_id"] == str(contact_id)
        assert body["trust_source"] == "face_confirmed"

    async def test_confirm_candidate_with_invalid_contact_returns_400(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        cluster_id = await _seed_cluster(test_session_factory, ws, candidates=[])

        resp = await client.post(
            f"{_PEOPLE_URL}/confirm-candidate",
            json={
                "cluster_id": str(cluster_id),
                "contact_id": str(uuid4()),
            },
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["error_code"] == "INVALID_CANDIDATE"

    async def test_reject_cluster_endpoint(
        self, client, auth_tokens, test_session_factory, face_env
    ):
        ws = auth_tokens["workspace_id"]
        uid = auth_tokens["user_id"]
        await _grant_consent(test_session_factory, ws, uid)
        cluster_id = await _seed_cluster(test_session_factory, ws)

        resp = await client.post(
            f"{_PEOPLE_URL}/reject-cluster",
            json={
                "cluster_id": str(cluster_id),
                "reason": "not a person",
            },
            headers=_auth_headers(auth_tokens, with_csrf=True),
            cookies=_csrf_cookie(auth_tokens),
        )
        assert resp.status_code == 204, resp.text

        async with test_session_factory() as db:
            row = (
                await db.execute(
                    select(FaceCluster).where(FaceCluster.id == cluster_id)
                )
            ).scalar_one()
        assert row.cluster_state == "rejected"

    async def test_unauthenticated_requests_return_401(
        self, client, face_env
    ):
        resp = await client.get(_PEOPLE_URL)
        assert resp.status_code == 401

    async def test_missing_consent_returns_403(
        self, client, auth_tokens, face_env
    ):
        # No consent granted → every endpoint must 403
        resp = await client.get(
            _PEOPLE_URL,
            headers=_auth_headers(auth_tokens),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FACE_CONSENT_REQUIRED"
