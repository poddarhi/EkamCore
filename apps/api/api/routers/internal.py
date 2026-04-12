"""Internal API endpoints — not routed by Caddy, accessible within the container network only."""

import asyncio
from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import async_session, get_db
from api.schemas.calendar import CalendarIngestRequest, CalendarIngestResponse
from api.schemas.contact import ContactIngestRequest, ContactIngestResponse
from api.schemas.reminder import ReminderIngestRequest, ReminderIngestResponse
from api.services.ingestion import calendar_sync, contact_sync, reminder_sync
from api.services.ingestion.fs_handler import handle_fs_event, scan_source

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


@router.post("/ingest/calendar", response_model=CalendarIngestResponse)
async def ingest_calendar(
    body: CalendarIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> CalendarIngestResponse:
    """Upsert calendar events for a source.

    Called by scheduled tasks or the Tauri manager app (future).
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    inserted, updated, unchanged = await calendar_sync.upsert_events(
        source_id=body.source_id,
        workspace_id=body.workspace_id,
        events=body.events,
        db=db,
    )
    return CalendarIngestResponse(inserted=inserted, updated=updated, unchanged=unchanged)


@router.post("/ingest/reminders", response_model=ReminderIngestResponse)
async def ingest_reminders(
    body: ReminderIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> ReminderIngestResponse:
    """Upsert reminders for a source.

    Called by scheduled tasks or the Tauri manager app (future).
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    inserted, updated, unchanged = await reminder_sync.upsert_reminders(
        source_id=body.source_id,
        workspace_id=body.workspace_id,
        reminders=body.reminders,
        db=db,
    )
    return ReminderIngestResponse(inserted=inserted, updated=updated, unchanged=unchanged)


@router.post("/ingest/contacts", response_model=ContactIngestResponse)
async def ingest_contacts(
    body: ContactIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> ContactIngestResponse:
    """Upsert contacts for a source. High-quality contacts auto-create a TrustedPerson
    when the trusted_persons table exists (Phase 3 feature gate).

    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    inserted, updated, unchanged, trusted_persons_created = await contact_sync.upsert_contacts(
        source_id=body.source_id,
        workspace_id=body.workspace_id,
        contacts=body.contacts,
        db=db,
    )
    return ContactIngestResponse(
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        trusted_persons_created=trusted_persons_created,
    )


# ---------------------------------------------------------------------------
# Filesystem event endpoints
# ---------------------------------------------------------------------------


class FsEventRequest(BaseModel):
    source_id: UUID
    event_type: Literal["created", "modified", "deleted", "renamed"]
    path: str = Field(min_length=1, max_length=4096)
    old_path: str | None = Field(None, max_length=4096)


class FsScanRequest(BaseModel):
    source_id: UUID


@router.post("/fs-event", status_code=202)
async def post_fs_event(
    body: FsEventRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive a filesystem change event from the manager app.

    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    result = await handle_fs_event(
        source_id=body.source_id,
        event_type=body.event_type,
        path=body.path,
        old_path=body.old_path,
        db=db,
    )

    logger.info(
        "fs_event_received",
        source_id=str(body.source_id),
        event_type=body.event_type,
        action=result.get("action"),
    )
    return result


@router.post("/fs-scan", status_code=202)
async def post_fs_scan(
    body: FsScanRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a full filesystem scan for a source.

    Compares the source path to the files table:
    - New files → queued for ingestion
    - Missing files → marked as deleted
    - Existing files → untouched

    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    result = await scan_source(source_id=body.source_id, db=db)

    logger.info(
        "fs_scan_triggered",
        source_id=str(body.source_id),
        new=result.get("new"),
        deleted=result.get("deleted"),
    )
    return result


# ---------------------------------------------------------------------------
# Paperless sync endpoint
# ---------------------------------------------------------------------------


class PaperlessSyncRequest(BaseModel):
    workspace_id: UUID


async def _run_paperless_sync(workspace_id: UUID) -> None:
    """Run Paperless sync in a fresh DB session (called from background task)."""
    from api.services.paperless.sync import sync_all_documents

    async with async_session() as db:
        try:
            result = await sync_all_documents(workspace_id=workspace_id, db=db)
            logger.info(
                "paperless_sync_background_complete",
                workspace_id=str(workspace_id),
                **result,
            )
        except Exception:
            logger.error(
                "paperless_sync_background_error",
                workspace_id=str(workspace_id),
                exc_info=True,
            )


@router.post("/paperless/sync", status_code=202)
async def trigger_paperless_sync(body: PaperlessSyncRequest) -> dict:  # noqa: D401
    """Manually trigger a Paperless document sync for a workspace.

    Runs asynchronously in the background — returns 202 immediately.
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    asyncio.create_task(_run_paperless_sync(body.workspace_id))
    logger.info("paperless_sync_triggered", workspace_id=str(body.workspace_id))
    return {"status": "sync_started", "workspace_id": str(body.workspace_id)}


# ---------------------------------------------------------------------------
# Paperless correspondent bridge endpoint
# ---------------------------------------------------------------------------


async def _run_correspondent_bridge(workspace_id: UUID) -> None:
    """Run the correspondent bridge in a fresh DB session (background task)."""
    from api.services.paperless.correspondent_bridge import run_correspondent_bridge

    async with async_session() as db:
        try:
            result = await run_correspondent_bridge(workspace_id=workspace_id, db=db)
            logger.info(
                "correspondent_bridge_background_complete",
                workspace_id=str(workspace_id),
                **result,
            )
        except Exception:
            logger.error(
                "correspondent_bridge_background_error",
                workspace_id=str(workspace_id),
                exc_info=True,
            )


@router.post("/paperless/correspondent-bridge", status_code=202)
async def trigger_correspondent_bridge(body: PaperlessSyncRequest) -> dict:
    """Trigger the Paperless correspondent → contacts candidate bridge.

    Runs asynchronously in the background — returns 202 immediately.
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    asyncio.create_task(_run_correspondent_bridge(body.workspace_id))
    logger.info(
        "correspondent_bridge_triggered",
        workspace_id=str(body.workspace_id),
    )
    return {"status": "bridge_started", "workspace_id": str(body.workspace_id)}


# ---------------------------------------------------------------------------
# Photo ingestion endpoint
# ---------------------------------------------------------------------------


class PhotoIngestRequest(BaseModel):
    source_id: UUID
    file_path: str = Field(min_length=1, max_length=4096)


async def _run_photo_ingest(source_id: UUID, file_path: str) -> None:
    """Run photo ingestion pipeline in a fresh DB session."""
    from api.services.ingestion.photo_pipeline import ingest_photo

    async with async_session() as db:
        try:
            result = await ingest_photo(source_id=source_id, file_path=file_path, db=db)
            logger.info(
                "photo_ingest_background_complete",
                source_id=str(source_id),
                **{k: str(v) if v else v for k, v in result.items()},
            )
        except Exception:
            logger.error(
                "photo_ingest_background_error",
                source_id=str(source_id),
                exc_info=True,
            )


@router.post("/ingest/photo", status_code=202)
async def trigger_photo_ingest(body: PhotoIngestRequest) -> dict:
    """Trigger photo ingestion for a single file.

    Runs asynchronously in the background — returns 202 immediately.
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    asyncio.create_task(_run_photo_ingest(body.source_id, body.file_path))
    logger.info("photo_ingest_triggered", source_id=str(body.source_id))
    return {"status": "ingestion_started", "source_id": str(body.source_id)}


# ---------------------------------------------------------------------------
# Manual face processing trigger (S11-006)
# ---------------------------------------------------------------------------


class FaceProcessPhotoRequest(BaseModel):
    photo_asset_id: UUID


class FaceProcessPhotoResponse(BaseModel):
    photo_asset_id: UUID
    face_count: int


@router.post("/face/process-photo", response_model=FaceProcessPhotoResponse)
async def trigger_face_processing(
    body: FaceProcessPhotoRequest,
    db: AsyncSession = Depends(get_db),
) -> FaceProcessPhotoResponse:
    """Manually run face detection for a single photo.

    Consent is re-checked inside ``process_photo_for_faces`` — if the
    face pipeline is not active for the photo's workspace, the call
    returns ``face_count=0`` and writes nothing. Not exposed externally —
    Caddy does not route /api/v1/internal/*.
    """
    from api.services.face.face_ingestion import process_photo_for_faces

    count = await process_photo_for_faces(body.photo_asset_id, db)
    await db.commit()
    logger.info(
        "face_process_photo_triggered",
        photo_asset_id=str(body.photo_asset_id),
        face_count=count,
    )
    return FaceProcessPhotoResponse(
        photo_asset_id=body.photo_asset_id,
        face_count=count,
    )


# ---------------------------------------------------------------------------
# Near-duplicate photo detection endpoint
# ---------------------------------------------------------------------------


class FindPhotoDuplicatesRequest(BaseModel):
    workspace_id: UUID
    threshold: int = Field(5, ge=0, le=64, description="Max Hamming distance for near-duplicates")


@router.post("/photos/find-duplicates", status_code=200)
async def find_photo_duplicates(
    body: FindPhotoDuplicatesRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Scan workspace photos for near-duplicates and return SuggestionCards.

    Uses pHash Hamming distance — photos within `threshold` bits are grouped.
    Does NOT delete anything; returns review suggestions only.
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    from api.services.ingestion.dedup_photos import scan_for_near_duplicates
    from uuid import uuid4 as _uuid4

    groups = await scan_for_near_duplicates(
        workspace_id=body.workspace_id,
        threshold=body.threshold,
        db=db,
    )

    cards = []
    for group in groups:
        cards.append({
            "type": "suggestion",
            "id": str(_uuid4()),
            "priority_score": 0.6,
            "source_ids": [str(pid) for pid in group],
            "payload": {
                "suggestion_type": "duplicate_photos",
                "group": [str(pid) for pid in group],
                "action": "review",
            },
        })

    logger.info(
        "photo_duplicate_scan_complete",
        workspace_id=str(body.workspace_id),
        group_count=len(groups),
    )
    return {"groups": len(groups), "cards": cards}
