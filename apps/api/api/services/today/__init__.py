"""Today card assembly: CalendarCardSource + ReminderCardSource + StatusCardSource.

S15-007: Added Redis caching (60s TTL) for the assembled card set per workspace.
Cache is keyed by workspace_id + date (minute resolution for freshness).
"""

import json
import time
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.envelope import Card, ResponseEnvelope, make_envelope
from api.services.redis_client import REDIS_DB_CACHE, get_redis
from api.services.today.calendar_card_source import CalendarCardSource
from api.services.today.pack_card_source import PackCardSource
from api.services.today.person_card_source import PersonCardSource
from api.services.today.reminder_card_source import ReminderCardSource
from api.services.today.status_card_source import StatusCardSource

logger = structlog.get_logger()

_CACHE_TTL_SECS = 60  # 1 minute — fresh enough for interactive use


def _cache_key(workspace_id: UUID, today_str: str) -> str:
    return f"today:{workspace_id}:{today_str}"


async def assemble_today(
    *,
    workspace_id: UUID,
    db: AsyncSession,
    reference_dt: datetime | None = None,
) -> ResponseEnvelope:
    """Assemble all today cards from all sources and return a ResponseEnvelope.

    Args:
        workspace_id: The workspace to query.
        db: Database session.
        reference_dt: Override "now" (UTC). Defaults to datetime.now(UTC).
    """
    t0 = time.perf_counter()

    now = reference_dt or datetime.now(timezone.utc)
    today = now.date()

    # S15-007: Try Redis cache first
    cache_key = _cache_key(workspace_id, today.isoformat())
    try:
        cached = await get_redis(REDIS_DB_CACHE).get(cache_key)
        if cached is not None:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            envelope = ResponseEnvelope.model_validate_json(cached)
            # Update latency to reflect cache hit time
            envelope.metadata.latency_ms = latency_ms
            envelope.metadata.cache_hint.ttl_seconds = _CACHE_TTL_SECS
            return envelope
    except Exception:
        pass  # Cache miss or error — proceed with assembly

    calendar_source = CalendarCardSource(workspace_id=workspace_id, db=db)
    reminder_source = ReminderCardSource(workspace_id=workspace_id, db=db)
    status_source = StatusCardSource(workspace_id=workspace_id)
    person_source = PersonCardSource(workspace_id=workspace_id, db=db)
    pack_source = PackCardSource(workspace_id=workspace_id, db=db)

    event_cards = await calendar_source.fetch(today=today, now=now)
    reminder_cards = await reminder_source.fetch(today=today, now=now)
    status_card = status_source.fetch(now=now)
    person_cards = await person_source.fetch(today=today, now=now)
    pack_cards = await pack_source.fetch(today=today, now=now)

    all_cards: list[Card] = [
        *event_cards,
        *reminder_cards,
        *person_cards,
        *pack_cards,
        status_card,
    ]
    all_cards.sort(key=lambda c: c.priority_score, reverse=True)

    latency_ms = int((time.perf_counter() - t0) * 1000)

    envelope = make_envelope(
        cards=all_cards,
        query_path="deterministic",
        latency_ms=latency_ms,
    )

    # S15-007: Cache the result
    try:
        await get_redis(REDIS_DB_CACHE).set(
            cache_key,
            envelope.model_dump_json(),
            ex=_CACHE_TTL_SECS,
        )
    except Exception:
        pass  # Cache write failure is non-fatal

    return envelope
