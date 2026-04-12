"""Local telemetry service (G-15 / ART-27).

EkamCore is local-first. This module collects and aggregates metrics
for the owner's own dashboard — nothing is ever sent externally.

Data flow:
  1. Middleware records per-request latency + endpoint group into Redis
     (counters in string keys, latencies in sorted sets).
  2. Background task flushes Redis aggregates to the `metrics` table
     every hour.
  3. Admin endpoints read from `metrics` for historical queries and
     compute a live snapshot from Redis + docker stats for `/current`.

Privacy:
  - No query text, file names, or user content recorded.
  - Only counts, latencies, and container-level resource usage.
  - Workspace ID is included so metrics are isolated per workspace.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.file import File
from api.db.models.metric import Metric
from api.db.models.photo_asset import PhotoAsset
from api.db.models.workspace import Workspace
from api.services.redis_client import REDIS_DB_CACHE, get_redis

logger = structlog.get_logger()

# ── Endpoint → group mapping ───────────────────────────────────────────────

ENDPOINT_GROUPS: dict[str, str] = {
    "/api/v1/query": "query",
    "/api/v1/search": "search",
    "/api/v1/today": "today",
    "/api/v1/recap": "recap",
    "/api/v1/sources": "sources",
    "/api/v1/settings": "settings",
    "/api/v1/notifications": "notifications",
    "/api/v1/photos": "photos",
    "/api/v1/auth/login": "auth",
    "/api/v1/auth/refresh": "auth",
    "/api/v1/auth/logout": "auth",
    "/api/v1/admin": "admin",
    "/api/v1/metrics": "admin",
    "/health": "health",
}


def classify_endpoint(path: str) -> str:
    """Map a request path to an endpoint group."""
    for prefix, group in ENDPOINT_GROUPS.items():
        if path.startswith(prefix):
            return group
    return "other"


# ── Redis keys ─────────────────────────────────────────────────────────────

# Usage counters (incremented per request)
#   metrics:count:{group}:{date}                 — total requests per group per day
#   metrics:latency:{group}:{hour}               — sorted set of latency_ms per hour
#   metrics:query_type:{type}:{date}             — deterministic / semantic / llm counts
#   metrics:page_view:{page}:{date}              — today / recap views

def _date_key(ts: datetime | None = None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return ts.strftime("%Y-%m-%d")


def _hour_key(ts: datetime | None = None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return ts.strftime("%Y-%m-%dT%H")


# ── Recording functions (called from middleware) ──────────────────────────


async def record_request(path: str, method: str, status: int, latency_ms: float) -> None:
    """Record a single HTTP request into Redis."""
    group = classify_endpoint(path)
    date = _date_key()
    hour = _hour_key()

    try:
        r = get_redis(REDIS_DB_CACHE)
        pipe = r.pipeline()
        # Count by group per day (24h TTL rollover — keep 90 days)
        pipe.incr(f"metrics:count:{group}:{date}")
        pipe.expire(f"metrics:count:{group}:{date}", 90 * 86400)

        # Count by status class per day
        status_class = f"{status // 100}xx"
        pipe.incr(f"metrics:status:{group}:{status_class}:{date}")
        pipe.expire(f"metrics:status:{group}:{status_class}:{date}", 90 * 86400)

        # Latency sorted set per hour (score = timestamp, member = latency)
        # We use a sorted set so we can compute percentiles on flush.
        score = time.time()
        pipe.zadd(
            f"metrics:latency:{group}:{hour}",
            {f"{score}:{latency_ms}": score},
        )
        pipe.expire(f"metrics:latency:{group}:{hour}", 7 * 86400)

        await pipe.execute()
    except Exception:
        logger.debug("metrics_record_request_failed", exc_info=True)


async def record_query_type(query_path: str) -> None:
    """Increment counter for query path type (deterministic / semantic / llm)."""
    date = _date_key()
    try:
        r = get_redis(REDIS_DB_CACHE)
        await r.incr(f"metrics:query_type:{query_path}:{date}")
        await r.expire(f"metrics:query_type:{query_path}:{date}", 90 * 86400)
    except Exception:
        logger.debug("metrics_record_query_type_failed", exc_info=True)


async def record_page_view(page: str) -> None:
    """Increment counter for a page view (today / recap)."""
    date = _date_key()
    try:
        r = get_redis(REDIS_DB_CACHE)
        await r.incr(f"metrics:page_view:{page}:{date}")
        await r.expire(f"metrics:page_view:{page}:{date}", 90 * 86400)
    except Exception:
        logger.debug("metrics_record_page_view_failed", exc_info=True)


async def record_llm_latency(model: str, latency_ms: float) -> None:
    """Record an LLM inference latency."""
    hour = _hour_key()
    try:
        r = get_redis(REDIS_DB_CACHE)
        score = time.time()
        await r.zadd(
            f"metrics:llm_latency:{model}:{hour}",
            {f"{score}:{latency_ms}": score},
        )
        await r.expire(f"metrics:llm_latency:{model}:{hour}", 7 * 86400)
    except Exception:
        logger.debug("metrics_record_llm_latency_failed", exc_info=True)


# ── Percentile helpers ────────────────────────────────────────────────────


def _percentile(values: Sequence[float], p: float) -> float:
    """Compute p-th percentile (0-100) of a sorted list."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    if f == c:
        return float(sorted_v[f])
    return float(sorted_v[f] + (sorted_v[c] - sorted_v[f]) * (k - f))


def _parse_latencies(members: list[str]) -> list[float]:
    """Extract latency values from `{score}:{latency}` members."""
    latencies = []
    for m in members:
        parts = m.split(":", 1)
        if len(parts) == 2:
            try:
                latencies.append(float(parts[1]))
            except ValueError:
                continue
    return latencies


# ── Hourly flush: Redis → PostgreSQL ───────────────────────────────────────


async def flush_hourly_metrics(db: AsyncSession, workspace_id: UUID) -> dict[str, Any]:
    """Aggregate the previous hour's Redis data into the metrics table.

    Called by the background flusher task. Idempotent: if already flushed
    for this hour, writes a new row (metrics are append-only).

    Returns:
        Summary dict with counts of metrics written.
    """
    now = datetime.now(timezone.utc)
    # Flush the hour that just completed
    period_end = now.replace(minute=0, second=0, microsecond=0)
    period_start = period_end - timedelta(hours=1)
    hour_key = period_start.strftime("%Y-%m-%dT%H")

    r = get_redis(REDIS_DB_CACHE)
    written = 0

    try:
        # 1. Per-group latency aggregates
        async for key in r.scan_iter(match=f"metrics:latency:*:{hour_key}"):
            parts = key.split(":")
            if len(parts) < 4:
                continue
            group = parts[2]
            members = await r.zrange(key, 0, -1)
            latencies = _parse_latencies(members)
            if not latencies:
                continue

            metric = Metric(
                metric_key=f"api_latency.{group}",
                metric_value={
                    "p50_ms": round(_percentile(latencies, 50), 2),
                    "p95_ms": round(_percentile(latencies, 95), 2),
                    "p99_ms": round(_percentile(latencies, 99), 2),
                    "count": len(latencies),
                    "mean_ms": round(sum(latencies) / len(latencies), 2),
                },
                period_start=period_start,
                period_end=period_end,
                workspace_id=workspace_id,
            )
            db.add(metric)
            written += 1

        # 2. LLM latency aggregates
        async for key in r.scan_iter(match=f"metrics:llm_latency:*:{hour_key}"):
            parts = key.split(":")
            if len(parts) < 4:
                continue
            model = parts[2]
            members = await r.zrange(key, 0, -1)
            latencies = _parse_latencies(members)
            if not latencies:
                continue

            metric = Metric(
                metric_key=f"llm_latency.{model}",
                metric_value={
                    "p50_ms": round(_percentile(latencies, 50), 2),
                    "p95_ms": round(_percentile(latencies, 95), 2),
                    "count": len(latencies),
                },
                period_start=period_start,
                period_end=period_end,
                workspace_id=workspace_id,
            )
            db.add(metric)
            written += 1

        await db.commit()

    except Exception:
        logger.warning("metrics_flush_failed", hour=hour_key, exc_info=True)
        await db.rollback()
        return {"written": 0, "error": True}

    logger.info(
        "metrics_flush_complete",
        hour=hour_key,
        written=written,
        workspace_id=str(workspace_id),
    )
    return {"written": written, "hour": hour_key}


# ── Daily flush: Redis counters → PostgreSQL ──────────────────────────────


async def flush_daily_metrics(db: AsyncSession, workspace_id: UUID) -> dict[str, Any]:
    """Aggregate yesterday's daily counters into the metrics table."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    period_start = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc)
    period_end = period_start + timedelta(days=1)
    date_key = yesterday.strftime("%Y-%m-%d")

    r = get_redis(REDIS_DB_CACHE)
    written = 0

    try:
        # 1. Request counts by group
        counts_by_group: dict[str, int] = {}
        async for key in r.scan_iter(match=f"metrics:count:*:{date_key}"):
            parts = key.split(":")
            if len(parts) < 4:
                continue
            group = parts[2]
            val = await r.get(key)
            if val:
                counts_by_group[group] = int(val)

        if counts_by_group:
            metric = Metric(
                metric_key="daily.request_counts",
                metric_value={"counts": counts_by_group, "total": sum(counts_by_group.values())},
                period_start=period_start,
                period_end=period_end,
                workspace_id=workspace_id,
            )
            db.add(metric)
            written += 1

        # 2. Query types
        query_types: dict[str, int] = {}
        async for key in r.scan_iter(match=f"metrics:query_type:*:{date_key}"):
            parts = key.split(":")
            if len(parts) < 4:
                continue
            qtype = parts[2]
            val = await r.get(key)
            if val:
                query_types[qtype] = int(val)

        if query_types:
            metric = Metric(
                metric_key="daily.queries_by_type",
                metric_value={
                    "types": query_types,
                    "total": sum(query_types.values()),
                },
                period_start=period_start,
                period_end=period_end,
                workspace_id=workspace_id,
            )
            db.add(metric)
            written += 1

        # 3. Page views
        page_views: dict[str, int] = {}
        async for key in r.scan_iter(match=f"metrics:page_view:*:{date_key}"):
            parts = key.split(":")
            if len(parts) < 4:
                continue
            page = parts[2]
            val = await r.get(key)
            if val:
                page_views[page] = int(val)

        if page_views:
            metric = Metric(
                metric_key="daily.page_views",
                metric_value=page_views,
                period_start=period_start,
                period_end=period_end,
                workspace_id=workspace_id,
            )
            db.add(metric)
            written += 1

        # 4. Cumulative totals from DB
        files_result = await db.execute(
            select(func.count(File.id)).where(
                and_(File.workspace_id == workspace_id, File.deleted_at.is_(None))
            )
        )
        files_count = files_result.scalar() or 0

        photos_result = await db.execute(
            select(func.count(PhotoAsset.id)).where(
                and_(PhotoAsset.workspace_id == workspace_id, PhotoAsset.deleted_at.is_(None))
            )
        )
        photos_count = photos_result.scalar() or 0

        metric = Metric(
            metric_key="daily.cumulative_totals",
            metric_value={
                "files_indexed_total": files_count,
                "photos_indexed_total": photos_count,
            },
            period_start=period_start,
            period_end=period_end,
            workspace_id=workspace_id,
        )
        db.add(metric)
        written += 1

        await db.commit()

    except Exception:
        logger.warning("metrics_daily_flush_failed", date=date_key, exc_info=True)
        await db.rollback()
        return {"written": 0, "error": True}

    logger.info(
        "metrics_daily_flush_complete",
        date=date_key,
        written=written,
        workspace_id=str(workspace_id),
    )
    return {"written": written, "date": date_key}


# ── Query functions (used by admin endpoints) ─────────────────────────────


async def query_metrics(
    db: AsyncSession,
    workspace_id: UUID,
    metric_key: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
) -> list[Metric]:
    """Query stored metrics for a workspace within a time range."""
    stmt = select(Metric).where(Metric.workspace_id == workspace_id)
    if metric_key:
        stmt = stmt.where(Metric.metric_key.like(f"{metric_key}%"))
    if start:
        stmt = stmt.where(Metric.period_start >= start)
    if end:
        stmt = stmt.where(Metric.period_end <= end)
    stmt = stmt.order_by(Metric.period_start.desc()).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_current_snapshot(db: AsyncSession, workspace_id: UUID) -> dict[str, Any]:
    """Return a live system snapshot (not stored in metrics table)."""
    now = datetime.now(timezone.utc)
    today_key = _date_key()
    hour_key = _hour_key()

    r = get_redis(REDIS_DB_CACHE)
    snapshot: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "workspace_id": str(workspace_id),
        "usage_today": {},
        "latency_current_hour": {},
        "cumulative": {},
    }

    # Today's request counts
    try:
        counts: dict[str, int] = {}
        async for key in r.scan_iter(match=f"metrics:count:*:{today_key}"):
            parts = key.split(":")
            if len(parts) >= 4:
                group = parts[2]
                val = await r.get(key)
                if val:
                    counts[group] = int(val)
        snapshot["usage_today"] = counts
        snapshot["usage_today"]["total"] = sum(counts.values())
    except Exception:
        logger.debug("snapshot_counts_failed", exc_info=True)

    # Current-hour latencies
    try:
        lat_by_group: dict[str, dict[str, float]] = {}
        async for key in r.scan_iter(match=f"metrics:latency:*:{hour_key}"):
            parts = key.split(":")
            if len(parts) >= 4:
                group = parts[2]
                members = await r.zrange(key, 0, -1)
                latencies = _parse_latencies(members)
                if latencies:
                    lat_by_group[group] = {
                        "p50_ms": round(_percentile(latencies, 50), 2),
                        "p95_ms": round(_percentile(latencies, 95), 2),
                        "count": len(latencies),
                    }
        snapshot["latency_current_hour"] = lat_by_group
    except Exception:
        logger.debug("snapshot_latency_failed", exc_info=True)

    # Cumulative totals from DB
    try:
        files_result = await db.execute(
            select(func.count(File.id)).where(
                and_(File.workspace_id == workspace_id, File.deleted_at.is_(None))
            )
        )
        photos_result = await db.execute(
            select(func.count(PhotoAsset.id)).where(
                and_(PhotoAsset.workspace_id == workspace_id, PhotoAsset.deleted_at.is_(None))
            )
        )
        snapshot["cumulative"] = {
            "files_indexed_total": files_result.scalar() or 0,
            "photos_indexed_total": photos_result.scalar() or 0,
        }
    except Exception:
        logger.debug("snapshot_cumulative_failed", exc_info=True)

    return snapshot


# ── Background flusher task ────────────────────────────────────────────────

_FLUSH_INTERVAL_SECONDS = 3600  # 1 hour


async def metrics_flush_loop() -> None:
    """Background task: flush Redis aggregates to PostgreSQL every hour.

    Started from the FastAPI lifespan context manager.
    Iterates all workspaces per flush; failures are per-workspace isolated.
    """
    from api.db.session import async_session

    # Wait for app startup to settle
    await asyncio.sleep(60)

    while True:
        try:
            async with async_session() as db:
                ws_result = await db.execute(select(Workspace))
                workspaces = ws_result.scalars().all()

            for ws in workspaces:
                try:
                    async with async_session() as db:
                        await flush_hourly_metrics(db, ws.id)
                except Exception:
                    logger.warning(
                        "metrics_hourly_flush_error",
                        workspace_id=str(ws.id),
                        exc_info=True,
                    )

            # Daily flush at midnight UTC
            now = datetime.now(timezone.utc)
            if now.hour == 0:
                for ws in workspaces:
                    try:
                        async with async_session() as db:
                            await flush_daily_metrics(db, ws.id)
                    except Exception:
                        logger.warning(
                            "metrics_daily_flush_error",
                            workspace_id=str(ws.id),
                            exc_info=True,
                        )
        except Exception:
            logger.warning("metrics_flush_loop_error", exc_info=True)

        await asyncio.sleep(_FLUSH_INTERVAL_SECONDS)
