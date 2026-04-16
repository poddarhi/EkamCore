"""PersonCardSource: surface trusted persons with recent activity (S13-009).

Emits up to ``MAX_PERSON_CARDS`` PersonCards per Today feed. For
Sprint 13 the only context we compute is ``"seen_recently"`` —
persons with at least one ``appears_in`` graph edge on a photo taken
in the last ``RECENT_DAYS`` days. Sprint 14 will layer on
``upcoming_event`` and ``catch_up`` variants.

Gating:
  - Face consent must be active for the workspace. The source
    returns an empty list when consent is inactive so the Today
    feed degrades gracefully rather than throwing.

PII rule: never log display_name. Only counts and ids.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.graph_edge import GraphEdge
from api.db.models.photo_asset import PhotoAsset
from api.db.models.trusted_person import TrustedPerson
from api.schemas.envelope import PersonCard
from api.services.face import consent_service

logger = structlog.get_logger()

MAX_PERSON_CARDS = 3
RECENT_DAYS = 14


class PersonCardSource:
    def __init__(self, *, workspace_id: UUID, db: AsyncSession) -> None:
        self._workspace_id = workspace_id
        self._db = db

    async def fetch(self, *, today: date, now: datetime) -> list[PersonCard]:
        if not await consent_service.is_consent_active(
            self._workspace_id, self._db
        ):
            return []

        cutoff = now - timedelta(days=RECENT_DAYS)

        # Count appears_in edges linking each person to a photo
        # taken after the cutoff. We rank by recent-photo count and
        # take the top MAX_PERSON_CARDS.
        stmt = (
            select(
                TrustedPerson.id,
                TrustedPerson.display_name,
                func.count(GraphEdge.id).label("recent_count"),
            )
            .select_from(TrustedPerson)
            .join(
                GraphEdge,
                and_(
                    GraphEdge.from_type == "trusted_person",
                    GraphEdge.from_id == TrustedPerson.id,
                    GraphEdge.to_type == "photo_asset",
                    GraphEdge.edge_type == "appears_in",
                    GraphEdge.workspace_id == self._workspace_id,
                ),
            )
            .join(
                PhotoAsset,
                and_(
                    PhotoAsset.id == GraphEdge.to_id,
                    PhotoAsset.workspace_id == self._workspace_id,
                    PhotoAsset.deleted_at.is_(None),
                    PhotoAsset.taken_at >= cutoff,
                ),
            )
            .where(
                and_(
                    TrustedPerson.workspace_id == self._workspace_id,
                    TrustedPerson.deleted_at.is_(None),
                )
            )
            .group_by(TrustedPerson.id, TrustedPerson.display_name)
            .order_by(func.count(GraphEdge.id).desc())
            .limit(MAX_PERSON_CARDS)
        )

        rows = (await self._db.execute(stmt)).all()

        cards: list[PersonCard] = []
        for rank, row in enumerate(rows):
            # Scores descend from 0.68 so person cards slot just
            # below calendar events in the Today ordering.
            score = round(0.68 - rank * 0.02, 4)
            cards.append(
                PersonCard(
                    id=row.id,
                    priority_score=score,
                    source_ids=[row.id],
                    payload={
                        "source": "trusted_person",
                        "person_id": str(row.id),
                        "display_name": row.display_name,
                        "avatar_url": f"/api/v1/people/{row.id}/avatar",
                        "context": "seen_recently",
                        "supporting_data": {
                            "recent_photo_count": int(row.recent_count),
                            "recent_days": RECENT_DAYS,
                        },
                    },
                )
            )

        logger.debug(
            "person_cards_fetched",
            workspace_id=str(self._workspace_id),
            count=len(cards),
        )
        return cards
