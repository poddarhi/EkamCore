"""Face clustering consent service — legal anchor of Phase 3 (S11-002).

Owns the full lifecycle of the `face_clustering_consent` record stored
at (workspace_id, user_id=NULL, namespace='privacy', key='face_clustering_consent').

Design goals (ART-15 §3, §4):
  1. Every grant and every revocation emits an append-only audit row.
  2. Revocation is atomic with hard-delete of all face data. If the
     deletion fails, the revocation transaction is rolled back — partial
     state is legally forbidden (you cannot record "I revoked consent"
     while embeddings still exist on disk).
  3. Consent never auto-expires based on time; it only expires when the
     consent text version changes (handled at read time by comparing
     `version` against CURRENT_CONSENT_VERSION).
  4. `is_consent_active()` is on the hot path — cached in Redis with a
     60-second TTL, invalidated on grant/revoke.
  5. Workspace isolation: consent state is keyed strictly by workspace_id.
     Workspace A's consent NEVER enables the face pipeline for workspace B.

Storage note:
  The raw row is stored in the `settings` table (namespace='privacy') as
  a JSONB blob, because we already have the per-workspace settings
  infrastructure and don't want a dedicated consents table for one record
  per workspace. The richer shape is enforced at the Pydantic layer.

  This supersedes the Phase 2 `core.face_clustering_consent` boolean.
  `api/services/flags.py::face_pipeline_active()` now calls
  `is_consent_active()` instead of reading the old boolean setting.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from api.services.face.hard_delete import DeleteReport

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.setting import Setting
from api.services import audit
from api.services.face import data_erasure
from api.services.face.consent_text import (
    CURRENT_CONSENT_VERSION,
)
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

_PRIVACY_NAMESPACE = "privacy"
_CONSENT_KEY = "face_clustering_consent"
_REDIS_CACHE_TTL_SECONDS = 60
_REDIS_KEY_PREFIX = "face_consent"


# ── Consent record shape ────────────────────────────────────────────────────


class ConsentRecord(BaseModel):
    """Immutable-by-convention record of a consent grant or revocation.

    Stored as JSONB in the `settings.value_json` column. `accepted=False`
    together with a non-null `revoked_at` marks a tombstone — the row is
    kept for audit correlation but is_consent_active() returns False.
    """

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    version: str
    granted_at: datetime
    granted_by_user_id: UUID
    ip: str
    user_agent: str
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None


def _to_jsonable(record: ConsentRecord) -> dict[str, Any]:
    """Convert a ConsentRecord to a JSON-serializable dict for JSONB storage.

    Pydantic's .model_dump() leaves datetimes as datetime objects; we need
    ISO strings for the JSONB column so SQLAlchemy can serialize them.
    """
    payload = record.model_dump()
    for field in ("granted_at", "revoked_at"):
        value = payload.get(field)
        if isinstance(value, datetime):
            payload[field] = value.isoformat()
    for field in ("granted_by_user_id", "revoked_by_user_id"):
        value = payload.get(field)
        if isinstance(value, UUID):
            payload[field] = str(value)
    return payload


def _from_jsonable(blob: dict[str, Any]) -> ConsentRecord:
    return ConsentRecord(**blob)


# ── Redis cache helpers ─────────────────────────────────────────────────────


def _cache_key(workspace_id: UUID) -> str:
    return f"{_REDIS_KEY_PREFIX}:{workspace_id}"


async def _cache_get(workspace_id: UUID) -> bool | None:
    """Return cached active-state, or None if the cache is cold."""
    try:
        r = get_redis(REDIS_DB_CACHE)
        value = await r.get(_cache_key(workspace_id))
    except Exception:
        logger.debug("consent_cache_read_failed", exc_info=True)
        return None

    if value is None:
        return None
    return value == "1"


async def _cache_set(workspace_id: UUID, active: bool) -> None:
    try:
        r = get_redis(REDIS_DB_CACHE)
        await r.setex(
            _cache_key(workspace_id),
            _REDIS_CACHE_TTL_SECONDS,
            "1" if active else "0",
        )
    except Exception:
        logger.debug("consent_cache_write_failed", exc_info=True)


async def _cache_invalidate(workspace_id: UUID) -> None:
    try:
        r = get_redis(REDIS_DB_CACHE)
        await r.delete(_cache_key(workspace_id))
    except Exception:
        logger.debug("consent_cache_invalidate_failed", exc_info=True)


# ── Core service operations ─────────────────────────────────────────────────


async def _load_row(
    workspace_id: UUID, db: AsyncSession
) -> Setting | None:
    """Fetch the raw Setting row for this workspace's face consent."""
    stmt = select(Setting).where(
        and_(
            Setting.namespace == _PRIVACY_NAMESPACE,
            Setting.key == _CONSENT_KEY,
            Setting.workspace_id == workspace_id,
            Setting.user_id.is_(None),  # workspace-scoped
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_active_consent(
    workspace_id: UUID, db: AsyncSession
) -> ConsentRecord | None:
    """Return the current active ConsentRecord for a workspace, or None.

    A record is "active" iff:
      - it exists
      - its `accepted` field is True
      - its `version` matches CURRENT_CONSENT_VERSION
      - its `revoked_at` is None
    """
    row = await _load_row(workspace_id, db)
    if row is None or row.value_json is None:
        return None

    try:
        record = _from_jsonable(dict(row.value_json))
    except Exception:
        logger.warning(
            "consent_record_parse_failed",
            workspace_id=str(workspace_id),
            exc_info=True,
        )
        return None

    if not record.accepted or record.revoked_at is not None:
        return None
    if record.version != CURRENT_CONSENT_VERSION:
        # Text version changed — old consent is no longer valid
        return None

    return record


async def is_consent_active(
    workspace_id: UUID,
    db: AsyncSession,
) -> bool:
    """Hot-path check: is face clustering consent currently active?

    Reads from Redis cache (60s TTL); falls through to DB on miss and
    populates the cache. Safe to call on every request.
    """
    cached = await _cache_get(workspace_id)
    if cached is not None:
        return cached

    record = await get_active_consent(workspace_id, db)
    active = record is not None
    await _cache_set(workspace_id, active)
    return active


async def grant(
    *,
    workspace_id: UUID,
    user_id: UUID,
    ip: str,
    user_agent: str,
    db: AsyncSession,
    version: str | None = None,
) -> ConsentRecord:
    """Record a consent grant for the workspace.

    Idempotent: if an active, same-version consent already exists, the
    existing record is returned unchanged and no new audit row is emitted.
    A bumped version (or an expired record) produces a new grant row.

    Atomicity: both the Setting row upsert and the audit_log row are
    written in the caller's transaction. On failure, both roll back.
    """
    effective_version = version or CURRENT_CONSENT_VERSION
    now = datetime.now(timezone.utc)

    existing = await get_active_consent(workspace_id, db)
    if existing is not None and existing.version == effective_version:
        logger.info(
            "face_consent_grant_idempotent",
            workspace_id=str(workspace_id),
            version=effective_version,
        )
        return existing

    record = ConsentRecord(
        accepted=True,
        version=effective_version,
        granted_at=now,
        granted_by_user_id=user_id,
        ip=ip,
        user_agent=user_agent,
        revoked_at=None,
        revoked_by_user_id=None,
    )
    payload = _to_jsonable(record)

    # Upsert the Setting row
    row = await _load_row(workspace_id, db)
    if row is None:
        row = Setting(
            workspace_id=workspace_id,
            user_id=None,
            namespace=_PRIVACY_NAMESPACE,
            key=_CONSENT_KEY,
            value_json=payload,
        )
        db.add(row)
    else:
        row.value_json = payload

    await db.flush()

    # Audit event
    await audit.log_event(
        db=db,
        action="face_consent_granted",
        object_type="face_consent",
        user_id=user_id,
        workspace_id=workspace_id,
        ip=ip,
        user_agent=user_agent,
        metadata={
            "consent_version": effective_version,
            "consent_text_version": effective_version,
        },
    )

    # Cache invalidation — let the next read populate with the fresh state.
    # We invalidate rather than write-through because the caller's
    # transaction has not yet committed.
    await _cache_invalidate(workspace_id)

    logger.info(
        "face_consent_granted",
        workspace_id=str(workspace_id),
        user_id=str(user_id),
        version=effective_version,
    )
    return record


async def revoke(
    *,
    workspace_id: UUID,
    user_id: UUID,
    ip: str,
    user_agent: str,
    db: AsyncSession,
) -> "DeleteReport | None":
    """Revoke consent and hard-delete all face data atomically.

    Order of operations (ART-15 §3):
      1. Load the existing active consent. If none, this is a no-op
         but still safe to call (idempotent) — returns None.
      2. Synchronously call hard_delete_all_face_data(). If it raises,
         the caller's transaction is rolled back and the revocation
         never took effect. Partial state is legally forbidden.
      3. Mark the Setting row as accepted=False with revoked_at set.
      4. Emit the `face_consent_revoked` audit row.
      5. Invalidate the Redis cache.

    The caller owns the transaction. On any exception above step 3,
    the caller MUST roll back. This function does not catch exceptions
    from hard_delete — they propagate for the rollback contract.

    Returns:
        The DeleteReport from the hard-delete step (for the DELETE API
        endpoint to echo back to the caller), or None if there was no
        active consent to revoke.
    """
    existing = await get_active_consent(workspace_id, db)
    if existing is None:
        logger.info(
            "face_consent_revoke_noop",
            workspace_id=str(workspace_id),
            reason="no_active_consent",
        )
        return None

    now = datetime.now(timezone.utc)

    # Step 1 — hard delete. Must succeed BEFORE the revocation is committed.
    # Any exception here bubbles up and rolls back the caller's transaction.
    delete_report = await data_erasure.hard_delete_all_face_data(
        workspace_id=workspace_id,
        db=db,
    )

    # Step 2 — mark the consent record as revoked
    row = await _load_row(workspace_id, db)
    if row is not None:
        revoked_record = existing.model_copy(
            update={
                "accepted": False,
                "revoked_at": now,
                "revoked_by_user_id": user_id,
            }
        )
        row.value_json = _to_jsonable(revoked_record)
        await db.flush()

    # Step 3 — audit trail
    await audit.log_event(
        db=db,
        action="face_consent_revoked",
        object_type="face_consent",
        user_id=user_id,
        workspace_id=workspace_id,
        ip=ip,
        user_agent=user_agent,
        metadata={
            "consent_version": existing.version,
            "original_granted_at": existing.granted_at.isoformat(),
            "original_granted_by_user_id": str(existing.granted_by_user_id),
        },
    )

    # Step 4 — cache invalidation
    await _cache_invalidate(workspace_id)

    logger.info(
        "face_consent_revoked",
        workspace_id=str(workspace_id),
        user_id=str(user_id),
        revoked_version=existing.version,
    )
    return delete_report
