"""Tests for /api/v1/sources CRUD endpoints."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from api.middleware.feature_gate import _ENABLED_FLAGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers(token: str, csrf: str) -> dict:
    return {"Authorization": f"Bearer {token}", "x-csrf-token": csrf}


def _auth_get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def ensure_flag_enabled():
    """Guarantee the feature flag is on for all tests in this file."""
    _ENABLED_FLAGS.add("sources_management_enabled")
    yield
    _ENABLED_FLAGS.discard("sources_management_enabled")


# ---------------------------------------------------------------------------
# GET /api/v1/sources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_sources_empty(client: AsyncClient, auth_tokens: dict) -> None:
    response = await client.get(
        "/api/v1/sources",
        headers=_auth_get_headers(auth_tokens["access_token"]),
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_sources_auth_required(client: AsyncClient) -> None:
    response = await client.get("/api/v1/sources")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_sources_flag_disabled(client: AsyncClient, auth_tokens: dict) -> None:
    _ENABLED_FLAGS.discard("sources_management_enabled")
    response = await client.get(
        "/api/v1/sources",
        headers=_auth_get_headers(auth_tokens["access_token"]),
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "FEATURE_DISABLED"


# ---------------------------------------------------------------------------
# POST /api/v1/sources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_source_contacts(client: AsyncClient, auth_tokens: dict) -> None:
    response = await client.post(
        "/api/v1/sources",
        json={"name": "My Contacts", "type": "contacts"},
        headers=_auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"]),
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Contacts"
    assert data["type"] == "contacts"
    assert data["status"] == "active"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_source_calendar(client: AsyncClient, auth_tokens: dict) -> None:
    response = await client.post(
        "/api/v1/sources",
        json={"name": "Work Calendar", "type": "calendar"},
        headers=_auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"]),
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "calendar"


@pytest.mark.asyncio
async def test_create_source_local_folder(client: AsyncClient, auth_tokens: dict, tmp_path) -> None:
    response = await client.post(
        "/api/v1/sources",
        json={"name": "Documents", "type": "local_folder", "path": str(tmp_path)},
        headers=_auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"]),
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 201
    assert response.json()["path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_create_source_folder_path_not_found(client: AsyncClient, auth_tokens: dict) -> None:
    response = await client.post(
        "/api/v1/sources",
        json={"name": "Bad Folder", "type": "local_folder", "path": "/nonexistent/path/abc123"},
        headers=_auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"]),
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "SOURCE_PATH_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_source_folder_path_required(client: AsyncClient, auth_tokens: dict) -> None:
    response = await client.post(
        "/api/v1/sources",
        json={"name": "Missing Path", "type": "local_folder"},
        headers=_auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"]),
        cookies={"ekamcore_csrf": auth_tokens["csrf_token"]},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "SOURCE_PATH_REQUIRED"


@pytest.mark.asyncio
async def test_create_source_duplicate(client: AsyncClient, auth_tokens: dict) -> None:
    payload = {"name": "Reminders", "type": "reminders"}
    headers = _auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"])
    cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}

    r1 = await client.post("/api/v1/sources", json=payload, headers=headers, cookies=cookies)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/sources", json=payload, headers=headers, cookies=cookies)
    assert r2.status_code == 409
    assert r2.json()["error_code"] == "SOURCE_DUPLICATE"


@pytest.mark.asyncio
async def test_create_source_auth_required(client: AsyncClient) -> None:
    # CSRF dependency runs before auth; either 401 (no auth) or 403 (no CSRF) confirms access denied
    response = await client.post("/api/v1/sources", json={"name": "X", "type": "contacts"})
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_source_csrf_required(client: AsyncClient, auth_tokens: dict) -> None:
    response = await client.post(
        "/api/v1/sources",
        json={"name": "X", "type": "contacts"},
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "CSRF_VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# PATCH /api/v1/sources/:id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_source(client: AsyncClient, auth_tokens: dict) -> None:
    headers = _auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"])
    cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}

    create = await client.post(
        "/api/v1/sources",
        json={"name": "Old Name", "type": "calendar"},
        headers=headers,
        cookies=cookies,
    )
    source_id = create.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/sources/{source_id}",
        json={"name": "New Name", "status": "paused"},
        headers=headers,
        cookies=cookies,
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "New Name"
    assert data["status"] == "paused"


@pytest.mark.asyncio
async def test_update_source_not_found(client: AsyncClient, auth_tokens: dict) -> None:
    headers = _auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"])
    cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}

    response = await client.patch(
        f"/api/v1/sources/{uuid4()}",
        json={"name": "X"},
        headers=headers,
        cookies=cookies,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_update_source_workspace_isolation(client: AsyncClient, auth_tokens: dict, seed_user: dict, test_session_factory) -> None:
    """A source owned by workspace B must not be patchable by a user whose token only contains workspace A."""
    from api.db.models.source import Source
    from api.db.models.workspace import Workspace

    # Create a second workspace (no membership for the authed user) and a source in it
    async with test_session_factory() as session:
        other_ws = Workspace(name="Other Workspace", type="personal", owner_id=seed_user["user_id"])
        session.add(other_ws)
        await session.flush()

        other_source = Source(
            workspace_id=other_ws.id,
            registered_by=seed_user["user_id"],
            name="Other WS Source",
            type="contacts",
            status="active",
        )
        session.add(other_source)
        await session.commit()
        other_source_id = other_source.id

    headers = _auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"])
    cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}

    response = await client.patch(
        f"/api/v1/sources/{other_source_id}",
        json={"name": "Hacked"},
        headers=headers,
        cookies=cookies,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/sources/:id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_source(client: AsyncClient, auth_tokens: dict) -> None:
    headers = _auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"])
    cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}

    create = await client.post(
        "/api/v1/sources",
        json={"name": "To Delete", "type": "reminders"},
        headers=headers,
        cookies=cookies,
    )
    # Use a unique name to avoid duplicate collision with other tests
    source_id = create.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/sources/{source_id}",
        headers=headers,
        cookies=cookies,
    )
    assert delete_resp.status_code == 204

    # Soft-deleted → must not appear in list
    list_resp = await client.get("/api/v1/sources", headers=_auth_get_headers(auth_tokens["access_token"]))
    ids = [s["id"] for s in list_resp.json()["items"]]
    assert source_id not in ids


@pytest.mark.asyncio
async def test_delete_source_not_found(client: AsyncClient, auth_tokens: dict) -> None:
    headers = _auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"])
    cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}

    response = await client.delete(
        f"/api/v1/sources/{uuid4()}",
        headers=headers,
        cookies=cookies,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cursor pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_sources_pagination(client: AsyncClient, auth_tokens: dict) -> None:
    headers = _auth_headers(auth_tokens["access_token"], auth_tokens["csrf_token"])
    cookies = {"ekamcore_csrf": auth_tokens["csrf_token"]}
    get_headers = _auth_get_headers(auth_tokens["access_token"])

    # Create 3 sources
    for i in range(3):
        await client.post(
            "/api/v1/sources",
            json={"name": f"Pag Source {i} {uuid4().hex[:6]}", "type": "calendar"},
            headers=headers,
            cookies=cookies,
        )

    page1 = await client.get("/api/v1/sources?limit=2", headers=get_headers)
    assert page1.status_code == 200
    data1 = page1.json()
    assert len(data1["items"]) <= 2

    if data1["next_cursor"]:
        page2 = await client.get(f"/api/v1/sources?limit=2&cursor={data1['next_cursor']}", headers=get_headers)
        assert page2.status_code == 200
        # IDs on page 2 must not overlap page 1
        ids1 = {s["id"] for s in data1["items"]}
        ids2 = {s["id"] for s in page2.json()["items"]}
        assert ids1.isdisjoint(ids2)
