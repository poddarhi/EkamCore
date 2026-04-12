"""Metric ORM model (G-15 / ART-27).

Stores aggregated local telemetry data. Never sent externally.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class Metric(Base):
    __tablename__ = "metrics"

    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
