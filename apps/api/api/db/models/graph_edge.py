"""Graph edge ORM model — People Graph foundation (S12-003 / ART-11).

A graph_edge is a directed typed relationship between two entities in
a workspace: (from_type, from_id) --edge_type--> (to_type, to_id).
Edges carry a strength in [0, 1] and an evidence_json blob so later
reviewers can trace why the edge was written.

Created in Sprint 12 for candidate contact scoring. Future stories
(S12+) broaden the producer set; the table is deliberately kept
flexible to avoid a second migration per edge type.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    from_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_id: Mapped[UUID] = mapped_column(nullable=False)
    to_type: Mapped[str] = mapped_column(String(32), nullable=False)
    to_id: Mapped[UUID] = mapped_column(nullable=False)
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    strength: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("1.0")
    )
