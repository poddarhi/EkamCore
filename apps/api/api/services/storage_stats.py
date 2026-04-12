"""Storage statistics service for the admin dashboard (S09-004).

Gathers disk usage from PostgreSQL, Qdrant, Paperless volumes, and the
host filesystem.  All sizes are returned in megabytes (float, 2 decimal).

This service runs inside the API container.  Docker volume sizes are
read by ``shutil.disk_usage`` on their mount points — the API container
must have the relevant volumes mounted (or the values will be 0).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.face_cluster import FaceCluster
from api.db.models.face_detection import FaceDetection
from api.db.models.file import File
from api.db.models.photo_asset import PhotoAsset
from api.db.models.setting import Setting

logger = structlog.get_logger()

_MB = 1024 * 1024


def _dir_size_mb(path: str | Path) -> float:
    """Return the total size of all files under *path* in MB, or 0 if missing."""
    p = Path(path)
    if not p.exists():
        return 0.0
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return round(total / _MB, 2)


def _disk_free_mb(path: str = "/") -> tuple[float, float]:
    """Return (total_mb, available_mb) for the filesystem containing *path*."""
    try:
        usage = shutil.disk_usage(path)
        return round(usage.total / _MB, 2), round(usage.free / _MB, 2)
    except OSError:
        return 0.0, 0.0


async def get_storage_stats(db: AsyncSession) -> dict:
    """Collect storage statistics from all EkamCore data stores.

    Returns a dict ready for JSON serialization.
    """
    # ── PostgreSQL database sizes ──
    pg_size_mb = 0.0
    try:
        result = await db.execute(text("SELECT pg_database_size(current_database())"))
        pg_bytes = result.scalar_one_or_none() or 0
        pg_size_mb = round(pg_bytes / _MB, 2)
    except Exception:
        logger.warning("storage_stats_pg_size_failed", exc_info=True)

    # ── Qdrant volume ──
    qdrant_size_mb = _dir_size_mb("/qdrant/storage") if Path("/qdrant/storage").exists() else 0.0

    # ── Paperless volumes ──
    paperless_data_mb = _dir_size_mb("/paperless/data") if Path("/paperless/data").exists() else 0.0
    paperless_media_mb = _dir_size_mb("/paperless/media") if Path("/paperless/media").exists() else 0.0
    paperless_size_mb = round(paperless_data_mb + paperless_media_mb, 2)

    # ── Thumbnails ──
    thumbnails_mb = _dir_size_mb("/app/data/thumbnails")

    # ── File counts ──
    file_count_result = await db.execute(
        select(func.count()).select_from(File).where(File.deleted_at.is_(None))
    )
    total_files = file_count_result.scalar_one()

    mime_result = await db.execute(
        select(File.mime_type, func.count())
        .where(File.deleted_at.is_(None))
        .group_by(File.mime_type)
    )
    by_mime_type = {row[0] or "unknown": row[1] for row in mime_result.all()}

    # ── Photo counts ──
    photo_count_result = await db.execute(
        select(func.count()).select_from(PhotoAsset).where(PhotoAsset.deleted_at.is_(None))
    )
    total_photos = photo_count_result.scalar_one()

    gps_result = await db.execute(
        select(func.count())
        .select_from(PhotoAsset)
        .where(PhotoAsset.deleted_at.is_(None), PhotoAsset.gps_lat.isnot(None))
    )
    photos_with_gps = gps_result.scalar_one()

    # ── Face data (S11-008) ─────────────────────────────────────────────
    # We surface the aggregate face counts on the admin storage page
    # ONLY when at least one workspace has active consent — this keeps
    # the tile invisible to owners who have never enabled the feature,
    # matching the consent-gated posture of the pipeline itself.
    face_consent_result = await db.execute(
        select(func.count()).select_from(Setting).where(
            Setting.namespace == "privacy",
            Setting.key == "face_clustering_consent",
            Setting.value_json["accepted"].astext == "true",
            Setting.value_json["revoked_at"].astext.is_(None),
        )
    )
    face_consent_active = int(face_consent_result.scalar() or 0)

    face_counts: dict | None = None
    if face_consent_active > 0:
        det_count = int(
            (
                await db.execute(
                    select(func.count()).select_from(FaceDetection).where(
                        FaceDetection.deleted_at.is_(None)
                    )
                )
            ).scalar_one()
        )
        cluster_count = int(
            (
                await db.execute(
                    select(func.count()).select_from(FaceCluster).where(
                        FaceCluster.deleted_at.is_(None)
                    )
                )
            ).scalar_one()
        )
        photos_processed = int(
            (
                await db.execute(
                    select(func.count()).select_from(PhotoAsset).where(
                        PhotoAsset.deleted_at.is_(None),
                        PhotoAsset.face_processed_at.isnot(None),
                    )
                )
            ).scalar_one()
        )
        face_counts = {
            "total_detections": det_count,
            "total_clusters": cluster_count,
            "photos_processed": photos_processed,
            "consent_active_workspaces": face_consent_active,
        }

    # ── Disk free space ──
    total_disk_mb, available_disk_mb = _disk_free_mb("/")
    free_pct = (available_disk_mb / total_disk_mb * 100) if total_disk_mb > 0 else 100

    return {
        "postgres_size_mb": pg_size_mb,
        "qdrant_size_mb": qdrant_size_mb,
        "paperless_size_mb": paperless_size_mb,
        "thumbnails_size_mb": thumbnails_mb,
        "file_counts": {
            "total": total_files,
            "by_mime_type": by_mime_type,
        },
        "photo_counts": {
            "total": total_photos,
            "with_gps": photos_with_gps,
        },
        "face_counts": face_counts,
        "total_disk_mb": total_disk_mb,
        "available_disk_mb": available_disk_mb,
        "free_space_pct": round(free_pct, 1),
        "free_space_warning": free_pct < 20,
        "free_space_critical": free_pct < 5,
    }
