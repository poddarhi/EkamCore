"""Candidate contact scoring for face clusters — S12-003.

Two changes:

1. ``face_clusters.candidates_json JSONB NULL`` — cached top-K candidate
   contacts for each cluster, populated by the scoring batch job. Shape:
   ``[{contact_id, score, signals, confidence}, ...]``. Nullable because
   small clusters (member_count < 3) are never scored and clusters with
   a trusted_person_id are already confirmed.

2. ``graph_edges`` table (schema reference §People Graph). Minimal shape
   needed so candidate scoring can consult prior confirmations as a
   boost signal (weight 0.20) without hand-rolling a JSON column.
   Keyed by (workspace_id, from_type, from_id, to_type, to_id, edge_type).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "face_clusters",
        sa.Column(
            "candidates_json",
            postgresql.JSONB,
            nullable=True,
        ),
    )

    op.create_table(
        "graph_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_uuid_v7()"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("from_type", sa.String(32), nullable=False),
        sa.Column(
            "from_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("to_type", sa.String(32), nullable=False),
        sa.Column("to_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("edge_type", sa.String(32), nullable=False),
        sa.Column(
            "evidence_json",
            postgresql.JSONB,
            nullable=True,
        ),
        sa.Column(
            "strength",
            sa.Float,
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_graph_edges_workspace_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "from_type",
            "from_id",
            "to_type",
            "to_id",
            "edge_type",
            name="uq_graph_edges_identity",
        ),
    )
    op.create_index(
        "ix_graph_edges_from",
        "graph_edges",
        ["workspace_id", "from_type", "from_id"],
    )
    op.create_index(
        "ix_graph_edges_to",
        "graph_edges",
        ["workspace_id", "to_type", "to_id"],
    )
    op.execute(
        """
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON graph_edges
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON graph_edges;")
    op.drop_index("ix_graph_edges_to", table_name="graph_edges")
    op.drop_index("ix_graph_edges_from", table_name="graph_edges")
    op.drop_table("graph_edges")
    op.drop_column("face_clusters", "candidates_json")
