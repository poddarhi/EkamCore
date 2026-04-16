"""Trusted Persons / People Graph CRUD (S12-004).

Seven endpoints under ``/api/v1/people``:

  GET    /                           list (cursor pagination)
  GET    /:person_id                  detail
  POST   /                           create from cluster
  POST   /confirm-candidate          confirm a ranked candidate
  POST   /reject-cluster             reject a cluster (reversible)
  PATCH  /:person_id                  rename
  DELETE /:person_id                  soft delete

Authentication + face consent are enforced on every endpoint. The
workspace is always derived from the authenticated user's first
workspace_id — *never* from the request body — to eliminate
confused-deputy vectors against cluster/person ids.

Rate limits (per-user, Redis DB_CACHE):
  - reads:     120/minute
  - mutations: 30/minute

Mutations additionally require the standard double-submit CSRF
cookie via ``validate_csrf``.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import (
    AuthorizationError,
    FaceConsentRequiredError,
    RateLimitError,
    ValidationError,
)
from api.middleware.auth import get_current_user
from api.middleware.csrf import validate_csrf
from api.schemas.auth import CurrentUser
from api.schemas.person_detail import (
    PersonEventItem,
    PersonEventListResponse,
    PersonFaceItem,
    PersonFacesResponse,
    PersonFileListResponse,
    PersonPhotoItem,
    PersonPhotoListResponse,
    PersonReminderListResponse,
    RemoveFaceRequest,
)
from api.schemas.trusted_person import (
    ConfirmCandidateRequest,
    RejectClusterRequest,
    TrustedPersonCreateRequest,
    TrustedPersonListResponse,
    TrustedPersonRenameRequest,
    TrustedPersonResponse,
)
from api.services.face import (
    avatar_service,
    consent_service,
    detach_face_service,
    trusted_person_service,
)
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/people", tags=["people"])


# ── Rate limiting ──────────────────────────────────────────────────────────

_READ_PREFIX = "rl:people_read:"
_READ_MAX = 120
_READ_WINDOW_SECS = 60

_WRITE_PREFIX = "rl:people_write:"
_WRITE_MAX = 30
_WRITE_WINDOW_SECS = 60


async def _check_rate_limit(
    user_id: UUID, *, prefix: str, max_calls: int, window_secs: int
) -> None:
    r = get_redis(REDIS_DB_CACHE)
    key = f"{prefix}{user_id}"
    count_str = await r.get(key)
    if count_str is not None and int(count_str) >= max_calls:
        ttl = await r.ttl(key)
        raise RateLimitError(
            error_code="RATE_LIMIT_EXCEEDED",
            message=f"Too many requests. Try again in {max(ttl, 1)} seconds.",
            details={"retry_after_seconds": max(ttl, 1)},
        )
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, window_secs)
    await pipe.execute()


async def _rate_limit_read(user_id: UUID) -> None:
    await _check_rate_limit(
        user_id,
        prefix=_READ_PREFIX,
        max_calls=_READ_MAX,
        window_secs=_READ_WINDOW_SECS,
    )


async def _rate_limit_write(user_id: UUID) -> None:
    await _check_rate_limit(
        user_id,
        prefix=_WRITE_PREFIX,
        max_calls=_WRITE_MAX,
        window_secs=_WRITE_WINDOW_SECS,
    )


# ── Consent resolution ────────────────────────────────────────────────────


async def _resolve_workspace(user: CurrentUser, db: AsyncSession) -> UUID:
    """Thin wrapper around the shared face-consent helper.

    S13-008 factored the body of this function into
    ``consent_service.resolve_workspace_with_face_consent`` so the
    photos router can reuse the same error copy. Kept as a thin
    alias so this router's call sites don't change.
    """
    return await consent_service.resolve_workspace_with_face_consent(
        user=user, db=db
    )


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("", response_model=TrustedPersonListResponse)
async def list_people(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonListResponse:
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    rows, next_cursor = await trusted_person_service.list_persons(
        workspace_id=workspace_id,
        db=db,
        limit=limit,
        cursor=cursor,
        search=search,
    )
    return TrustedPersonListResponse(
        items=[TrustedPersonResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get("/{person_id}/avatar")
async def get_person_avatar(
    person_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Cropped face avatar for the trusted person (S13-002).

    Returns JPEG bytes of the highest-scoring face_detection, cropped
    to the bbox and resized to 160×160. 404 when the person has no
    linked faces or the backing image is unreadable — the frontend
    should fall back to initials in that case.
    """
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    data = await avatar_service.generate_avatar(
        person_id=person_id, workspace_id=workspace_id, db=db
    )
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )


# ── Person detail tabs (S13-003) ──────────────────────────────────────────
#
# Photos / Files / Events / Reminders queries read from the
# graph_edges denormalization populated by S12-007's GraphEdgeBuilder.
# Cursor pagination uses the row id of the last item returned (UUID
# v7 is monotonic, so id DESC is a stable sort key without needing a
# composite cursor).
#
# Files and Reminders return empty lists today: build_person_file_edges
# is a documented placeholder pending the paperless correspondent
# bridge, and the reminder model has no person linkage yet. The
# OpenAPI shape is stable so the client and tests don't rebuild when
# those bridges land.


def _decode_id_cursor(cursor: str | None) -> UUID | None:
    if not cursor:
        return None
    try:
        return UUID(cursor)
    except ValueError as exc:
        raise ValidationError(
            error_code="VALIDATION_ERROR",
            message="Invalid cursor.",
        ) from exc


async def _ensure_person(
    person_id: UUID, workspace_id: UUID, db: AsyncSession
) -> None:
    """Load the person purely to enforce workspace isolation. The
    detail-page tabs all hang off this guard — without it, a tampered
    person_id would let a caller probe edges in another workspace."""
    await trusted_person_service.get_person(
        person_id=person_id, workspace_id=workspace_id, db=db
    )


@router.get("/{person_id}/photos", response_model=PersonPhotoListResponse)
async def list_person_photos(
    person_id: UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PersonPhotoListResponse:
    from sqlalchemy import and_, select

    from api.db.models.graph_edge import GraphEdge
    from api.db.models.photo_asset import PhotoAsset

    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await _ensure_person(person_id, workspace_id, db)

    cursor_id = _decode_id_cursor(cursor)
    stmt = (
        select(PhotoAsset)
        .join(GraphEdge, GraphEdge.to_id == PhotoAsset.id)
        .where(
            and_(
                GraphEdge.workspace_id == workspace_id,
                GraphEdge.from_type == "trusted_person",
                GraphEdge.from_id == person_id,
                GraphEdge.to_type == "photo_asset",
                GraphEdge.edge_type == "appears_in",
                PhotoAsset.workspace_id == workspace_id,
                PhotoAsset.deleted_at.is_(None),
            )
        )
        .order_by(PhotoAsset.id.desc())
        .limit(limit + 1)
    )
    if cursor_id is not None:
        stmt = stmt.where(PhotoAsset.id < cursor_id)
    rows = (await db.execute(stmt)).scalars().all()
    next_cursor = str(rows[limit - 1].id) if len(rows) > limit else None
    items = [
        PersonPhotoItem(
            id=p.id,
            file_id=p.file_id,
            thumbnail_url=f"/api/v1/photos/{p.id}/thumbnail",
            taken_at=p.taken_at,
            face_count=p.face_count,
            width=p.width,
            height=p.height,
        )
        for p in rows[:limit]
    ]
    return PersonPhotoListResponse(items=items, next_cursor=next_cursor)


@router.get("/{person_id}/files", response_model=PersonFileListResponse)
async def list_person_files(
    person_id: UUID,
    cursor: str | None = Query(default=None),  # noqa: ARG001
    limit: int = Query(default=50, ge=1, le=100),  # noqa: ARG001
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PersonFileListResponse:
    # S12-007: build_person_file_edges is a documented no-op until the
    # paperless correspondent bridge lands. We still enforce auth +
    # consent + workspace isolation so the contract is stable.
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await _ensure_person(person_id, workspace_id, db)
    return PersonFileListResponse(items=[], next_cursor=None)


@router.get("/{person_id}/events", response_model=PersonEventListResponse)
async def list_person_events(
    person_id: UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PersonEventListResponse:
    from sqlalchemy import and_, select

    from api.db.models.calendar_event import CalendarEvent
    from api.db.models.graph_edge import GraphEdge

    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await _ensure_person(person_id, workspace_id, db)

    cursor_id = _decode_id_cursor(cursor)
    stmt = (
        select(CalendarEvent)
        .join(GraphEdge, GraphEdge.to_id == CalendarEvent.id)
        .where(
            and_(
                GraphEdge.workspace_id == workspace_id,
                GraphEdge.from_type == "trusted_person",
                GraphEdge.from_id == person_id,
                GraphEdge.to_type == "calendar_event",
                GraphEdge.edge_type == "attended",
                CalendarEvent.workspace_id == workspace_id,
            )
        )
        .order_by(CalendarEvent.start_at.desc(), CalendarEvent.id.desc())
        .limit(limit + 1)
    )
    if cursor_id is not None:
        stmt = stmt.where(CalendarEvent.id < cursor_id)
    rows = (await db.execute(stmt)).scalars().all()
    next_cursor = str(rows[limit - 1].id) if len(rows) > limit else None
    items = [
        PersonEventItem(
            id=ev.id,
            title=ev.title,
            start_at=ev.start_at,
            end_at=ev.end_at,
            location=ev.location,
            is_all_day=ev.is_all_day,
        )
        for ev in rows[:limit]
    ]
    return PersonEventListResponse(items=items, next_cursor=next_cursor)


@router.get("/{person_id}/reminders", response_model=PersonReminderListResponse)
async def list_person_reminders(
    person_id: UUID,
    cursor: str | None = Query(default=None),  # noqa: ARG001
    limit: int = Query(default=50, ge=1, le=100),  # noqa: ARG001
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PersonReminderListResponse:
    # The reminder ORM model has no person linkage in v1.0 (no tags,
    # no graph_edges bridge). Endpoint is wired so the UI can render
    # the tab; it will light up automatically when the bridge lands.
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await _ensure_person(person_id, workspace_id, db)
    return PersonReminderListResponse(items=[], next_cursor=None)


@router.get("/{person_id}/faces", response_model=PersonFacesResponse)
async def list_person_faces(
    person_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PersonFacesResponse:
    from sqlalchemy import and_, select

    from api.db.models.face_cluster import FaceCluster
    from api.db.models.face_detection import FaceDetection

    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await _ensure_person(person_id, workspace_id, db)

    rows = (
        (
            await db.execute(
                select(FaceDetection)
                .join(FaceCluster, FaceCluster.id == FaceDetection.cluster_id)
                .where(
                    and_(
                        FaceCluster.trusted_person_id == person_id,
                        FaceCluster.workspace_id == workspace_id,
                        FaceCluster.deleted_at.is_(None),
                        FaceDetection.workspace_id == workspace_id,
                        FaceDetection.deleted_at.is_(None),
                    )
                )
                .order_by(FaceDetection.detection_score.desc())
            )
        )
        .scalars()
        .all()
    )
    items = [
        PersonFaceItem(
            face_detection_id=f.id,
            photo_asset_id=f.photo_asset_id,
            cluster_id=f.cluster_id,  # type: ignore[arg-type]
            detection_score=f.detection_score,
            thumbnail_url=(
                f"/api/v1/people/{person_id}/faces/{f.id}/thumbnail"
            ),
        )
        for f in rows
        if f.cluster_id is not None
    ]
    return PersonFacesResponse(items=items)


@router.get("/{person_id}/faces/{face_detection_id}/thumbnail")
async def get_person_face_thumbnail(
    person_id: UUID,  # noqa: ARG001 — kept in path for cache locality
    face_detection_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    data = await avatar_service.generate_face_thumbnail(
        face_detection_id=face_detection_id,
        workspace_id=workspace_id,
        db=db,
    )
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )


@router.post(
    "/{person_id}/remove-face",
    dependencies=[Depends(validate_csrf)],
    status_code=204,
    response_model=None,
)
async def remove_face(
    person_id: UUID,
    body: RemoveFaceRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await detach_face_service.detach_face(
        person_id=person_id,
        face_detection_id=body.face_detection_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )


@router.get("/{person_id}", response_model=TrustedPersonResponse)
async def get_person(
    person_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_read(user.id)
    workspace_id = await _resolve_workspace(user, db)
    row = await trusted_person_service.get_person(
        person_id=person_id, workspace_id=workspace_id, db=db
    )
    return TrustedPersonResponse.model_validate(row)


@router.post(
    "",
    dependencies=[Depends(validate_csrf)],
    status_code=201,
    response_model=TrustedPersonResponse,
)
async def create_person(
    body: TrustedPersonCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    person = await trusted_person_service.create_from_cluster(
        cluster_id=body.cluster_id,
        workspace_id=workspace_id,
        user_id=user.id,
        display_name=body.display_name,
        canonical_contact_id=body.canonical_contact_id,
        trust_source="manual",
        db=db,
    )
    return TrustedPersonResponse.model_validate(person)


@router.post(
    "/confirm-candidate",
    dependencies=[Depends(validate_csrf)],
    response_model=TrustedPersonResponse,
)
async def confirm_candidate(
    body: ConfirmCandidateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    person = await trusted_person_service.confirm_candidate(
        cluster_id=body.cluster_id,
        contact_id=body.contact_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
    return TrustedPersonResponse.model_validate(person)


@router.post(
    "/reject-cluster",
    dependencies=[Depends(validate_csrf)],
    status_code=204,
    response_model=None,
)
async def reject_cluster(
    body: RejectClusterRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await trusted_person_service.reject_cluster(
        cluster_id=body.cluster_id,
        workspace_id=workspace_id,
        user_id=user.id,
        reason=body.reason,
        db=db,
    )


@router.patch(
    "/{person_id}",
    dependencies=[Depends(validate_csrf)],
    response_model=TrustedPersonResponse,
)
async def rename_person(
    person_id: UUID,
    body: TrustedPersonRenameRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustedPersonResponse:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    person = await trusted_person_service.rename(
        person_id=person_id,
        workspace_id=workspace_id,
        user_id=user.id,
        new_name=body.display_name,
        db=db,
    )
    return TrustedPersonResponse.model_validate(person)


@router.delete(
    "/{person_id}",
    dependencies=[Depends(validate_csrf)],
    status_code=204,
    response_model=None,
)
async def delete_person(
    person_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _rate_limit_write(user.id)
    workspace_id = await _resolve_workspace(user, db)
    await trusted_person_service.delete(
        person_id=person_id,
        workspace_id=workspace_id,
        user_id=user.id,
        db=db,
    )
