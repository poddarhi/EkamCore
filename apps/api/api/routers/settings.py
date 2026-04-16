"""Settings API: read and write user/workspace settings (G-10).

GET  /api/v1/settings         → all settings with current values
PATCH /api/v1/settings        → bulk update (body: {key: value, ...})
GET  /api/v1/settings/:key    → single setting value
DELETE /api/v1/settings/:key  → reset to default

All endpoints require authentication. PATCH/DELETE require CSRF.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.schemas.auth import CurrentUser
from api.services.settings_service import (
    SETTINGS_REGISTRY,
    get_all_settings,
    get_setting,
    set_setting,
    delete_setting,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsPatchBody(BaseModel):
    """Body for PATCH /api/v1/settings — flat key: value dict."""
    settings: dict[str, Any]


class SettingsResponse(BaseModel):
    settings: dict[str, Any]
    registry: dict[str, dict[str, Any]]


def _registry_info() -> dict[str, dict[str, Any]]:
    """Build a JSON-serializable summary of the settings registry.

    Dispatches on the registry's ``kind`` attribute (S14-001 added
    ``"string"`` alongside the existing enum/boolean/integer types)
    rather than inferring via ``hasattr`` — the attribute-sniff
    would misclassify ``_StringDef`` as boolean because it has
    neither ``options`` nor ``min_val``.
    """
    result: dict[str, dict[str, Any]] = {}
    for key, defn in SETTINGS_REGISTRY.items():
        entry: dict[str, Any] = {
            "default": defn.default,
            "scope": defn.scope,
            "type": getattr(defn, "kind", "boolean"),
        }
        kind = entry["type"]
        if kind == "enum":
            entry["options"] = defn.options  # type: ignore[attr-defined]
        elif kind == "integer":
            entry["min"] = defn.min_val  # type: ignore[attr-defined]
            entry["max"] = defn.max_val  # type: ignore[attr-defined]
        elif kind == "string":
            entry["max_length"] = defn.max_length  # type: ignore[attr-defined]
            if defn.pattern is not None:  # type: ignore[attr-defined]
                entry["pattern"] = defn.pattern  # type: ignore[attr-defined]
        result[key] = entry
    return result


def _workspace_id(user: CurrentUser) -> UUID:
    """Extract the first workspace_id from the JWT.  Raises 403 if none."""
    if not user.workspace_ids:
        raise AuthorizationError(
            error_code="NO_WORKSPACE",
            message="No workspace found for this user.",
        )
    return user.workspace_ids[0]


@router.get("", response_model=SettingsResponse)
async def list_settings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Return all settings with current values merged with defaults.

    Also returns the registry schema so the frontend knows valid
    options, types, and defaults without hardcoding them.
    """
    ws_id = _workspace_id(user)
    values = await get_all_settings(user.id, ws_id, db)

    logger.info(
        "settings_listed",
        user_id=str(user.id),
        workspace_id=str(ws_id),
    )

    return SettingsResponse(settings=values, registry=_registry_info())


@router.patch(
    "",
    dependencies=[Depends(validate_csrf)],
    response_model=SettingsResponse,
)
async def update_settings(
    body: SettingsPatchBody,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Bulk update settings.  Body: ``{"settings": {"key": value, ...}}``.

    Each key is validated against the registry. Unknown keys or invalid
    values return 422.  Successfully validated keys are upserted.
    """
    ws_id = _workspace_id(user)

    for key, value in body.settings.items():
        await set_setting(key, value, user.id, ws_id, db)

    await db.commit()

    values = await get_all_settings(user.id, ws_id, db)

    logger.info(
        "settings_updated",
        user_id=str(user.id),
        workspace_id=str(ws_id),
        keys=list(body.settings.keys()),
    )

    return SettingsResponse(settings=values, registry=_registry_info())


@router.get("/{key}", )
async def get_single_setting(
    key: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single setting's current value."""
    ws_id = _workspace_id(user)
    value = await get_setting(key, user.id, ws_id, db)
    return {"key": key, "value": value}


@router.delete(
    "/{key}",
    dependencies=[Depends(validate_csrf)],
    status_code=204,
    response_model=None,
)
async def reset_setting(
    key: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a setting, reverting it to its default value."""
    ws_id = _workspace_id(user)
    await delete_setting(key, user.id, ws_id, db)
    await db.commit()

    logger.info(
        "setting_reset",
        user_id=str(user.id),
        workspace_id=str(ws_id),
        key=key,
    )
