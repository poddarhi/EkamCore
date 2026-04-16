"""Pack infrastructure tables — pack_runs + pack_cards (S14-001).

Two tables own the full lifecycle of a Personal Life Assistant
(and any future pack) execution:

  * ``pack_runs``  — one row per pack invocation with trigger,
    timing, outcome, and quota counters.
  * ``pack_cards`` — one row per card a run produced, carrying the
    user-visible payload and the acknowledgement trail.

Both tables cascade-delete on workspace removal so a tenant purge
never leaves orphan pack state. CHECK constraints keep ``state``,
``card_type``, and ``acknowledged_action`` honest at the DB layer
so even a buggy worker can't write junk.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PACK_RUN_STATES = ("running", "completed", "failed", "timeout")
PACK_CARD_TYPES = (
    "follow_up_suggestion",
    "weekly_summary",
    "relationship_reminder",
)
PACK_ACK_ACTIONS = ("done", "dismissed", "snoozed")


def upgrade() -> None:
    op.create_table(
        "pack_runs",
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
        sa.Column("pack_id", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "state",
            sa.String(32),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "cards_produced",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "llm_calls_used",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_pack_runs"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_pack_runs_workspace_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "state IN ('running', 'completed', 'failed', 'timeout')",
            name="ck_pack_runs_state",
        ),
    )
    op.create_index(
        "ix_pack_runs_workspace",
        "pack_runs",
        ["workspace_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_pack_runs_pack",
        "pack_runs",
        ["pack_id", sa.text("started_at DESC")],
    )

    op.create_table(
        "pack_cards",
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
        sa.Column(
            "pack_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("card_type", sa.String(64), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB,
            nullable=False,
        ),
        sa.Column("target_date", sa.Date, nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "acknowledged_action",
            sa.String(32),
            nullable=True,
        ),
        sa.Column("snoozed_until", sa.Date, nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_pack_cards"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_pack_cards_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pack_run_id"],
            ["pack_runs.id"],
            name="fk_pack_cards_pack_run_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "card_type IN ("
            "'follow_up_suggestion', 'weekly_summary', 'relationship_reminder'"
            ")",
            name="ck_pack_cards_card_type",
        ),
        sa.CheckConstraint(
            "acknowledged_action IS NULL OR acknowledged_action IN ("
            "'done', 'dismissed', 'snoozed'"
            ")",
            name="ck_pack_cards_ack_action",
        ),
    )
    op.create_index(
        "ix_pack_cards_workspace_date",
        "pack_cards",
        ["workspace_id", "target_date"],
    )
    op.create_index(
        "ix_pack_cards_type",
        "pack_cards",
        ["card_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_pack_cards_type", table_name="pack_cards")
    op.drop_index(
        "ix_pack_cards_workspace_date", table_name="pack_cards"
    )
    op.drop_table("pack_cards")
    op.drop_index("ix_pack_runs_pack", table_name="pack_runs")
    op.drop_index("ix_pack_runs_workspace", table_name="pack_runs")
    op.drop_table("pack_runs")
