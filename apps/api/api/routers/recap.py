"""Recap endpoint: returns a ResponseEnvelope of cards for a past day or week."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.middleware.feature_gate import _ENABLED_FLAGS
from api.schemas.envelope import ResponseEnvelope
from api.services.recap.generator import generate_recap

logger = structlog.get_logger()

# Lazy import for LLM summary — only used when llm_query_enabled flag is set
_recap_summary_mod = None

_FLAG = require_flag("recap_enabled")

router = APIRouter(prefix="/api/v1/recap", tags=["recap"])


@router.get("", dependencies=[_FLAG], response_model=ResponseEnvelope)
async def get_recap(
    workspace_id: UUID = Query(..., description="Workspace to query"),
    period: Literal["daily", "weekly"] = Query("daily", description="Recap period"),
    date_param: date | None = Query(
        None,
        alias="date",
        description="Target date (YYYY-MM-DD). Defaults to yesterday.",
    ),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope:
    """Return a recap of events, completed reminders, and new overdue items.

    Daily: cards for a single date.
    Weekly: cards aggregated over 7 days ending on the target date.
    """
    if workspace_id not in user.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    envelope = await generate_recap(
        workspace_id=workspace_id,
        db=db,
        period=period,
        target_date=date_param,
    )

    # LLM-generated recap summary (graceful — cards returned even if LLM fails)
    if envelope.cards and "llm_query_enabled" in _ENABLED_FLAGS:
        try:
            from api.services.query.prompts.recap_summary_v1 import (
                build_messages as build_recap_messages,
                MODEL as RECAP_MODEL,
                TEMPERATURE as RECAP_TEMP,
                TIMEOUT_S as RECAP_TIMEOUT,
            )
            from api.services.query.llm_client import call_llm
            import json as _json

            event_count = sum(1 for c in envelope.cards if c.type == "event")  # type: ignore[union-attr]
            reminder_count = sum(1 for c in envelope.cards if c.type == "reminder")  # type: ignore[union-attr]
            highlights = [
                c.payload.get("title", "") for c in envelope.cards  # type: ignore[union-attr]
                if getattr(c, "type", None) in ("event", "reminder") and c.payload.get("title")
            ][:5]

            messages = build_recap_messages(
                period=period,
                event_count=event_count,
                reminder_count=reminder_count,
                file_count=0,
                highlights=highlights,
            )
            raw = await call_llm(messages, RECAP_MODEL, timeout_s=RECAP_TIMEOUT, temperature=RECAP_TEMP)
            parsed = _json.loads(raw)
            if isinstance(parsed, dict) and "summary" in parsed:
                import html
                envelope.answer_text = html.escape(str(parsed["summary"]))
        except Exception:
            logger.warning("recap_summary_llm_failed", exc_info=True)

    logger.info(
        "recap_served",
        workspace_id=str(workspace_id),
        period=period,
        target_date=str(date_param),
        card_count=len(envelope.cards),
    )
    return envelope
