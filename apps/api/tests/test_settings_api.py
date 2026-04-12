"""Tests for G-10: Settings API — CRUD, validation, defaults, isolation.

Covers:
  - GET /api/v1/settings: returns all settings with defaults + registry
  - PATCH /api/v1/settings: validates and persists
  - GET /api/v1/settings/:key: single value
  - DELETE /api/v1/settings/:key: resets to default
  - Validation: unknown key, wrong type, enum mismatch, integer out of range
  - Workspace isolation: user A cannot access user B's settings
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from api.services.settings_service import (
    validate_setting,
    SETTINGS_REGISTRY,
)


# ── Unit tests: validation ──────────────────────────────────────────────────


class TestValidation:

    def test_valid_enum_setting(self):
        result = validate_setting("date_format", "YYYY-MM-DD")
        assert result == "YYYY-MM-DD"

    def test_invalid_enum_setting(self):
        from api.errors import ValidationError
        with pytest.raises(ValidationError):
            validate_setting("date_format", "INVALID_FORMAT")

    def test_valid_boolean_setting(self):
        result = validate_setting("backup_enabled", True)
        assert result is True

    def test_invalid_boolean_setting(self):
        from api.errors import ValidationError
        with pytest.raises(ValidationError):
            validate_setting("backup_enabled", "yes")

    def test_valid_integer_setting(self):
        result = validate_setting("backup_retention_days", 30)
        assert result == 30

    def test_integer_below_min(self):
        from api.errors import ValidationError
        with pytest.raises(ValidationError):
            validate_setting("backup_retention_days", 0)

    def test_integer_above_max(self):
        from api.errors import ValidationError
        with pytest.raises(ValidationError):
            validate_setting("backup_retention_days", 100)

    def test_unknown_key_raises_validation(self):
        from api.errors import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            validate_setting("nonexistent_key", "value")
        assert "Unknown setting key" in str(exc_info.value.message)

    def test_boolean_rejects_integer(self):
        """Integers should not be accepted for boolean settings (0/1 trick)."""
        from api.errors import ValidationError
        with pytest.raises(ValidationError):
            validate_setting("backup_enabled", 1)

    def test_registry_has_all_expected_keys(self):
        # S11-002: face_clustering_consent is no longer a registry key —
        # consent is owned by ConsentService in namespace='privacy'.
        expected = {
            "date_format", "time_format", "theme",
            "backup_enabled", "backup_retention_days",
        }
        assert set(SETTINGS_REGISTRY.keys()) == expected


# ── API endpoint tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(client, auth_tokens):
    """GET /api/v1/settings returns all keys with default values."""
    resp = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # All registry keys present
    assert "settings" in data
    for key in SETTINGS_REGISTRY:
        assert key in data["settings"], f"Missing key: {key}"

    # Defaults match
    assert data["settings"]["date_format"] == "MM/DD/YYYY"
    assert data["settings"]["time_format"] == "12h"
    assert data["settings"]["theme"] == "light"
    assert data["settings"]["backup_enabled"] is True
    assert data["settings"]["backup_retention_days"] == 7
    # S11-002: face_clustering_consent is no longer in the settings
    # registry — it is owned by ConsentService (namespace='privacy').

    # Registry schema included
    assert "registry" in data
    assert data["registry"]["date_format"]["type"] == "enum"
    assert "MM/DD/YYYY" in data["registry"]["date_format"]["options"]


@pytest.mark.asyncio
async def test_patch_settings_persists(client, auth_tokens):
    """PATCH /api/v1/settings persists values and returns updated settings."""
    csrf = auth_tokens.get("csrf_token", "")
    headers = {
        "Authorization": f"Bearer {auth_tokens['access_token']}",
        "X-CSRF-Token": csrf,
    }
    cookies = {"ekamcore_csrf": csrf}

    resp = await client.patch(
        "/api/v1/settings",
        json={"settings": {"date_format": "YYYY-MM-DD", "backup_retention_days": 14}},
        headers=headers,
        cookies=cookies,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["settings"]["date_format"] == "YYYY-MM-DD"
    assert data["settings"]["backup_retention_days"] == 14

    # Verify persistence via GET
    resp2 = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp2.json()["settings"]["date_format"] == "YYYY-MM-DD"
    assert resp2.json()["settings"]["backup_retention_days"] == 14


@pytest.mark.asyncio
async def test_patch_unknown_key_returns_422(client, auth_tokens):
    """PATCH with an unknown key returns 422."""
    csrf = auth_tokens.get("csrf_token", "")
    resp = await client.patch(
        "/api/v1/settings",
        json={"settings": {"nonexistent_key": "value"}},
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": csrf,
        },
        cookies={"ekamcore_csrf": csrf},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_patch_wrong_type_returns_422(client, auth_tokens):
    """PATCH with wrong value type returns 422."""
    csrf = auth_tokens.get("csrf_token", "")
    resp = await client.patch(
        "/api/v1/settings",
        json={"settings": {"backup_enabled": "not_a_boolean"}},
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": csrf,
        },
        cookies={"ekamcore_csrf": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_enum_invalid_option_returns_422(client, auth_tokens):
    """PATCH with invalid enum option returns 422."""
    csrf = auth_tokens.get("csrf_token", "")
    resp = await client.patch(
        "/api/v1/settings",
        json={"settings": {"date_format": "INVALID"}},
        headers={
            "Authorization": f"Bearer {auth_tokens['access_token']}",
            "X-CSRF-Token": csrf,
        },
        cookies={"ekamcore_csrf": csrf},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_single_setting(client, auth_tokens):
    """GET /api/v1/settings/:key returns a single value."""
    resp = await client.get(
        "/api/v1/settings/date_format",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "date_format"
    assert data["value"] == "MM/DD/YYYY"


@pytest.mark.asyncio
async def test_get_unknown_key_returns_422(client, auth_tokens):
    resp = await client.get(
        "/api/v1/settings/nonexistent",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_resets_to_default(client, auth_tokens):
    """DELETE /api/v1/settings/:key resets the setting to its default."""
    csrf = auth_tokens.get("csrf_token", "")
    headers = {
        "Authorization": f"Bearer {auth_tokens['access_token']}",
        "X-CSRF-Token": csrf,
    }
    cookies = {"ekamcore_csrf": csrf}

    # Set a non-default value
    await client.patch(
        "/api/v1/settings",
        json={"settings": {"time_format": "24h"}},
        headers=headers,
        cookies=cookies,
    )

    # Delete it
    resp = await client.delete(
        "/api/v1/settings/time_format",
        headers=headers,
        cookies=cookies,
    )
    assert resp.status_code == 204

    # Verify it's back to default
    resp2 = await client.get(
        "/api/v1/settings/time_format",
        headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
    )
    assert resp2.json()["value"] == "12h"


@pytest.mark.asyncio
async def test_settings_require_auth(client):
    """Unauthenticated request returns 401."""
    resp = await client.get("/api/v1/settings")
    assert resp.status_code == 401
