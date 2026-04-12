"""Add metrics table for local telemetry (G-15 / ART-27).

Revision ID: 012
Revises: 011
Create Date: 2026-04-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_uuid_v7()"),
            nullable=False,
        ),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("metric_value", postgresql.JSONB, nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
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
    )
    op.create_index(
        "ix_metrics_workspace_key_period",
        "metrics",
        ["workspace_id", "metric_key", "period_start"],
    )
    op.create_index(
        "ix_metrics_key_period",
        "metrics",
        ["metric_key", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_metrics_key_period", table_name="metrics")
    op.drop_index("ix_metrics_workspace_key_period", table_name="metrics")
    op.drop_table("metrics")
