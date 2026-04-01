"""StatusCardSource: produce a system status card summarising the current time context."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from api.schemas.envelope import StatusCard

# Fixed priority — status card is informational, not urgent
_STATUS_PRIORITY = 0.50


class StatusCardSource:
    def __init__(self, *, workspace_id: UUID) -> None:
        self._workspace_id = workspace_id

    def fetch(self, *, now: datetime) -> StatusCard:
        """Return a StatusCard with time-of-day context payload."""
        hour = now.hour
        if hour < 12:
            time_of_day = "morning"
        elif hour < 17:
            time_of_day = "afternoon"
        elif hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        payload = {
            "date": now.date().isoformat(),
            "time_of_day": time_of_day,
            "weekday": now.strftime("%A"),
        }

        return StatusCard(
            id=uuid4(),
            priority_score=_STATUS_PRIORITY,
            source_ids=[],
            payload=payload,
        )
