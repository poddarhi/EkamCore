"""Settings CRUD service with registry-based validation (G-10).

Every setting is defined in ``SETTINGS_REGISTRY`` with its type, default,
validation rules, and scope (``user`` or ``workspace``).

User-scoped settings are stored per ``(workspace_id, user_id, key)``; workspace-
scoped settings use ``(workspace_id, NULL, key)`` so they apply to all members.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.setting import Setting
from api.errors import NotFoundError, ValidationError

logger = structlog.get_logger()

_NAMESPACE = "core"  # all settings in this service use the "core" namespace


# ── Registry ────────────────────────────────────────────────────────────────

class _EnumDef:
    kind: Literal["enum"] = "enum"
    def __init__(self, options: list[str], default: str, scope: str):
        self.options = options
        self.default = default
        self.scope = scope

class _BoolDef:
    kind: Literal["boolean"] = "boolean"
    def __init__(self, default: bool, scope: str):
        self.default = default
        self.scope = scope

class _IntDef:
    kind: Literal["integer"] = "integer"
    def __init__(self, default: int, scope: str, min_val: int, max_val: int):
        self.default = default
        self.scope = scope
        self.min_val = min_val
        self.max_val = max_val


SettingDef = _EnumDef | _BoolDef | _IntDef

SETTINGS_REGISTRY: dict[str, SettingDef] = {
    "date_format": _EnumDef(
        options=["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"],
        default="MM/DD/YYYY",
        scope="user",
    ),
    "time_format": _EnumDef(
        options=["12h", "24h"],
        default="12h",
        scope="user",
    ),
    "theme": _EnumDef(
        options=["light"],
        default="light",
        scope="user",
    ),
    "face_clustering_consent": _BoolDef(default=False, scope="workspace"),
    "backup_enabled": _BoolDef(default=True, scope="workspace"),
    "backup_retention_days": _IntDef(default=7, scope="workspace", min_val=1, max_val=90),
}


# ── Validation ──────────────────────────────────────────────────────────────


def validate_setting(key: str, value: Any) -> Any:
    """Validate a setting key + value against the registry.

    Returns the validated (possibly coerced) value.
    Raises ``ValidationError`` if the key is unknown or the value is invalid.
    """
    defn = SETTINGS_REGISTRY.get(key)
    if defn is None:
        raise ValidationError(
            error_code="VALIDATION_ERROR",
            message=f"Unknown setting key: '{key}'.",
            details={"key": key, "valid_keys": list(SETTINGS_REGISTRY.keys())},
        )

    if isinstance(defn, _EnumDef):
        if not isinstance(value, str) or value not in defn.options:
            raise ValidationError(
                error_code="VALIDATION_ERROR",
                message=f"Setting '{key}' must be one of {defn.options}.",
                details={"key": key, "options": defn.options, "received": value},
            )
        return value

    if isinstance(defn, _BoolDef):
        if not isinstance(value, bool):
            raise ValidationError(
                error_code="VALIDATION_ERROR",
                message=f"Setting '{key}' must be a boolean.",
                details={"key": key, "received": value},
            )
        return value

    if isinstance(defn, _IntDef):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(
                error_code="VALIDATION_ERROR",
                message=f"Setting '{key}' must be an integer.",
                details={"key": key, "received": value},
            )
        if value < defn.min_val or value > defn.max_val:
            raise ValidationError(
                error_code="VALIDATION_ERROR",
                message=f"Setting '{key}' must be between {defn.min_val} and {defn.max_val}.",
                details={"key": key, "min": defn.min_val, "max": defn.max_val, "received": value},
            )
        return value

    raise ValidationError(
        error_code="VALIDATION_ERROR",
        message=f"Unknown setting type for key '{key}'.",
    )


# ── Service ─────────────────────────────────────────────────────────────────


def _scope_filter(
    key: str,
    user_id: UUID,
    workspace_id: UUID,
):
    """Build the WHERE clause for a setting lookup respecting scope."""
    defn = SETTINGS_REGISTRY[key]
    conditions = [
        Setting.namespace == _NAMESPACE,
        Setting.key == key,
        Setting.workspace_id == workspace_id,
    ]
    if defn.scope == "user":
        conditions.append(Setting.user_id == user_id)
    else:
        conditions.append(Setting.user_id.is_(None))
    return and_(*conditions)


async def get_all_settings(
    user_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """Return all settings with current values merged with defaults.

    Returns a flat ``{key: value}`` dict covering every key in the registry.
    """
    # Fetch all saved settings for this user/workspace
    stmt = select(Setting).where(
        Setting.namespace == _NAMESPACE,
        Setting.workspace_id == workspace_id,
    )
    rows = list((await db.execute(stmt)).scalars().all())

    # Build a lookup: (user_id_or_none, key) → value
    saved: dict[tuple[UUID | None, str], Any] = {}
    for row in rows:
        saved[(row.user_id, row.key)] = row.value_json

    result: dict[str, Any] = {}
    for key, defn in SETTINGS_REGISTRY.items():
        if defn.scope == "user":
            val = saved.get((user_id, key))
        else:
            val = saved.get((None, key))
        result[key] = val if val is not None else defn.default

    return result


async def get_setting(
    key: str,
    user_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> Any:
    """Return a single setting's current value (or its default)."""
    defn = SETTINGS_REGISTRY.get(key)
    if defn is None:
        raise ValidationError(
            error_code="VALIDATION_ERROR",
            message=f"Unknown setting key: '{key}'.",
        )

    stmt = select(Setting).where(_scope_filter(key, user_id, workspace_id))
    row = (await db.execute(stmt)).scalar_one_or_none()
    return row.value_json if row is not None else defn.default


async def set_setting(
    key: str,
    value: Any,
    user_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> Setting:
    """Validate and upsert a single setting. Returns the Setting row."""
    validated = validate_setting(key, value)
    defn = SETTINGS_REGISTRY[key]

    stmt = select(Setting).where(_scope_filter(key, user_id, workspace_id))
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row is not None:
        row.value_json = validated
    else:
        row = Setting(
            workspace_id=workspace_id,
            user_id=user_id if defn.scope == "user" else None,
            namespace=_NAMESPACE,
            key=key,
            value_json=validated,
        )
        db.add(row)

    await db.flush()
    return row


async def delete_setting(
    key: str,
    user_id: UUID,
    workspace_id: UUID,
    db: AsyncSession,
) -> None:
    """Delete a setting (revert to default)."""
    defn = SETTINGS_REGISTRY.get(key)
    if defn is None:
        raise ValidationError(
            error_code="VALIDATION_ERROR",
            message=f"Unknown setting key: '{key}'.",
        )

    stmt = delete(Setting).where(_scope_filter(key, user_id, workspace_id))
    await db.execute(stmt)
    await db.flush()


async def get_consent(
    key: str,
    workspace_id: UUID,
    db: AsyncSession,
) -> bool | None:
    """Return a consent boolean setting's value, or None if never set.

    Unlike ``get_setting``, this returns ``None`` (not the default) when the
    user has never explicitly consented or declined — callers must distinguish
    "not yet answered" from "declined".
    """
    defn = SETTINGS_REGISTRY.get(key)
    if defn is None or not isinstance(defn, _BoolDef):
        return None

    stmt = select(Setting).where(
        Setting.namespace == _NAMESPACE,
        Setting.key == key,
        Setting.workspace_id == workspace_id,
        Setting.user_id.is_(None),
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None  # never answered
    return bool(row.value_json)
