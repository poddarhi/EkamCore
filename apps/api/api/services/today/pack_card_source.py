"""PackCardSource: surface un-acknowledged pack_cards in the Today feed (S14-009).

Queries ``pack_cards`` for the target date, filters out acknowledged
and not-yet-unsnoozed cards, and wraps each row as a standard
``PackCard`` envelope card so ``CardRenderer`` can delegate to the
appropriate frontend component.

Card ordering:
  - ``weekly_summary`` first (pinned at priority 0.99).
  - ``follow_up_suggestion`` and ``relationship_reminder`` by the
    ``priority`` field inside ``payload_json`` (descending), with a
    base of 0.65 so they slot below calendar events but above the
    status card.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.pack_card import PackCard as PackCardModel
from api.schemas.envelope import PackCard

logger = structlog.get_logger()


class PackCardSource:
    def __init__(self, *, workspace_id: UUID, db: AsyncSession) -> None:
        self._workspace_id = workspace_id
        self._db = db

    async def fetch(
        self, *, today: date, now: datetime
    ) -> list[PackCard]:
        stmt = (
            select(PackCardModel)
            .where(
                and_(
                    PackCardModel.workspace_id == self._workspace_id,
                    PackCardModel.target_date == today,
                    PackCardModel.acknowledged_at.is_(None),
                    or_(
                        PackCardModel.snoozed_until.is_(None),
                        PackCardModel.snoozed_until <= today,
                    ),
                )
            )
            .order_by(PackCardModel.created_at)
        )
        rows = (await self._db.execute(stmt)).scalars().all()

        cards: list[PackCard] = []
        for row in rows:
            payload = dict(row.payload_json or {})
            payload["pack_card_id"] = str(row.id)
            payload["card_type"] = row.card_type

            if row.card_type == "weekly_summary":
                score = 0.99
            else:
                raw_priority = payload.get("priority", 0)
                score = round(
                    0.65 + min(float(raw_priority), 10) * 0.02, 4
                )

            cards.append(
                PackCard(
                    id=row.id,
                    priority_score=score,
                    source_ids=[row.pack_run_id],
                    payload=payload,
                )
            )

        logger.debug(
            "pack_cards_fetched",
            workspace_id=str(self._workspace_id),
            count=len(cards),
        )
        return cards
