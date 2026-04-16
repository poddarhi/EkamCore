"""Pack card acknowledgment + listing endpoints (S14-009).

POST /api/v1/pack-cards/:card_id/acknowledge — mark a card as
done / dismissed / snoozed.
GET /api/v1/pack-cards — list today's cards (acknowledged or not,
filterable via query param).

Auth required; workspace isolation on every query.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.pack_card import PackCard
from api.db.session import get_db
from api.errors import AuthorizationError, NotFoundError
from api.middleware.auth import get_current_user
from api.schemas.auth import CurrentUser

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/pack-cards", tags=["pack-cards"])


def _workspace_id(user: CurrentUser) -> UUID:
    if not user.workspace_ids:
        raise AuthorizationError(
            error_code="NO_WORKSPACE",
            message="User has no workspace.",
        )
    return user.workspace_ids[0]


class AcknowledgeRequest(BaseModel):
    action: Literal["done", "dismissed", "snoozed"]
    snoozed_until: date | None = None


@router.post("/{card_id}/acknowledge")
async def acknowledge_card(
    card_id: UUID,
    body: AcknowledgeRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ws = _workspace_id(user)
    card = (
        await db.execute(
            select(PackCard).where(
                and_(
                    PackCard.id == card_id,
                    PackCard.workspace_id == ws,
                )
            )
        )
    ).scalar_one_or_none()
    if card is None:
        raise NotFoundError(
            error_code="PACK_CARD_NOT_FOUND",
            message="Pack card not found.",
        )
    card.acknowledged_at = datetime.now(timezone.utc)
    card.acknowledged_action = body.action
    if body.action == "snoozed" and body.snoozed_until:
        card.snoozed_until = body.snoozed_until
    await db.flush()
    logger.info(
        "pack_card_acknowledged",
        card_id=str(card_id),
        action=body.action,
        workspace_id=str(ws),
    )
    return {
        "id": str(card.id),
        "card_type": card.card_type,
        "acknowledged_action": card.acknowledged_action,
        "acknowledged_at": card.acknowledged_at.isoformat(),
        "snoozed_until": (
            card.snoozed_until.isoformat() if card.snoozed_until else None
        ),
    }


@router.get("")
async def list_pack_cards(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    target_date: date | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
) -> dict[str, Any]:
    ws = _workspace_id(user)
    today = target_date or date.today()
    conditions = [
        PackCard.workspace_id == ws,
        PackCard.target_date == today,
    ]
    if acknowledged is True:
        conditions.append(PackCard.acknowledged_at.is_not(None))
    elif acknowledged is False:
        conditions.append(PackCard.acknowledged_at.is_(None))
        conditions.append(
            or_(
                PackCard.snoozed_until.is_(None),
                PackCard.snoozed_until <= today,
            )
        )
    stmt = (
        select(PackCard)
        .where(and_(*conditions))
        .order_by(PackCard.created_at)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        {
            "id": str(r.id),
            "card_type": r.card_type,
            "payload": r.payload_json,
            "target_date": r.target_date.isoformat(),
            "acknowledged_at": (
                r.acknowledged_at.isoformat() if r.acknowledged_at else None
            ),
            "acknowledged_action": r.acknowledged_action,
            "snoozed_until": (
                r.snoozed_until.isoformat() if r.snoozed_until else None
            ),
        }
        for r in rows
    ]
    return {"items": items}
