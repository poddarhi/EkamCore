"""Workspace isolation for /api/v1/people (S12-004).

Two users, A and B, each in their own workspace with active face
consent. B creates a trusted person and a rejected-target cluster
in workspace B. User A must NOT be able to:

  - read B's person via GET /:person_id
  - rename B's person via PATCH /:person_id
  - delete B's person via DELETE /:person_id
  - reject B's cluster via POST /reject-cluster

All forbidden attempts must 404 (we return NotFoundError to avoid
leaking the existence of a resource in another workspace).
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from api.db.models.face_cluster import FaceCluster
from api.db.models.trusted_person import TrustedPerson
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.services import flags
from api.services.auth import hash_password
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


async def _mk_user_and_ws(factory, label: str) -> tuple[UUID, UUID, str]:
    email = f"iso-{label}-{uuid4().hex[:6]}@ekamcore.dev"
    password = "testpassword123"
    async with factory() as db:
        u = User(
            email=email,
            display_name=f"Iso {label}",
            password_hash=hash_password(password),
            role="standard",
            is_active=True,
        )
        db.add(u)
        await db.flush()
        ws = Workspace(name=f"Iso {label}", type="personal", owner_id=u.id)
        db.add(ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role="admin"))
        await consent_service.grant(
            workspace_id=ws.id,
            user_id=u.id,
            ip="127.0.0.1",
            user_agent="pytest",
            db=db,
        )
        await db.commit()
        return u.id, ws.id, email


async def _login(client, email: str, password: str = "testpassword123") -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    cookies = resp.cookies
    return {
        "access_token": data["access_token"],
        "csrf_token": cookies.get("ekamcore_csrf"),
    }


async def _seed_person_and_cluster(factory, workspace_id, user_id):
    async with factory() as db:
        cluster = FaceCluster(
            workspace_id=workspace_id,
            centroid_encrypted=crypto.encrypt_embedding([0.0] * 512),
            member_count=5,
            cluster_state="unconfirmed",
        )
        db.add(cluster)
        await db.flush()
        person = TrustedPerson(
            workspace_id=workspace_id,
            display_name="B's Person",
            trust_source="manual",
        )
        db.add(person)
        await db.flush()
        cluster_id = cluster.id
        person_id = person.id
        await db.commit()
    return cluster_id, person_id


def _h(tokens, *, with_csrf: bool = False):
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    if with_csrf:
        h["X-CSRF-Token"] = tokens["csrf_token"]
    return h


def _c(tokens):
    return {"ekamcore_csrf": tokens["csrf_token"]}


class TestPeopleIsolation:
    async def test_user_a_cannot_reach_workspace_b_people(
        self, client, test_session_factory, face_env
    ):
        uid_a, ws_a, email_a = await _mk_user_and_ws(test_session_factory, "A")
        uid_b, ws_b, email_b = await _mk_user_and_ws(test_session_factory, "B")
        cluster_b, person_b = await _seed_person_and_cluster(
            test_session_factory, ws_b, uid_b
        )

        tokens_a = await _login(client, email_a)

        # GET detail → 404 (don't leak existence)
        resp = await client.get(
            f"{_PEOPLE_URL}/{person_b}",
            headers=_h(tokens_a),
        )
        assert resp.status_code == 404

        # PATCH rename → 404
        resp = await client.patch(
            f"{_PEOPLE_URL}/{person_b}",
            json={"display_name": "Hijacked"},
            headers=_h(tokens_a, with_csrf=True),
            cookies=_c(tokens_a),
        )
        assert resp.status_code == 404

        # DELETE → 404
        resp = await client.delete(
            f"{_PEOPLE_URL}/{person_b}",
            headers=_h(tokens_a, with_csrf=True),
            cookies=_c(tokens_a),
        )
        assert resp.status_code == 404

        # POST /reject-cluster on B's cluster → 404
        resp = await client.post(
            f"{_PEOPLE_URL}/reject-cluster",
            json={"cluster_id": str(cluster_b)},
            headers=_h(tokens_a, with_csrf=True),
            cookies=_c(tokens_a),
        )
        assert resp.status_code == 404

        # POST / (create from B's cluster) → 404
        resp = await client.post(
            _PEOPLE_URL,
            json={
                "cluster_id": str(cluster_b),
                "display_name": "Hijack",
            },
            headers=_h(tokens_a, with_csrf=True),
            cookies=_c(tokens_a),
        )
        assert resp.status_code == 404

        # LIST from A's side must not include B's person
        resp = await client.get(_PEOPLE_URL, headers=_h(tokens_a))
        assert resp.status_code == 200, resp.text
        ids = {p["id"] for p in resp.json()["items"]}
        assert str(person_b) not in ids
