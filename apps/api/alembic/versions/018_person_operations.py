"""Person operations undo log — S12-006.

A single table keyed by workspace that records every merge/split/
rename/delete (and optionally confirm/reject) on trusted persons.
Each row carries:

  - ``forward_payload``  — what the operation did (for display / audit)
  - ``inverse_payload``  — what ``undo_service`` needs to reverse it

Undo is soft: applying an undo stamps ``undone_at`` + ``undone_by``
on the original row; the row is never deleted so the history tab
in the People Graph review UI remains stable.

Retention: at most 50 entries per workspace survive; the nightly
prune job (wired in a later story) truncates by created_at ASC.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "person_operations",
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
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("forward_payload", postgresql.JSONB, nullable=False),
        sa.Column("inverse_payload", postgresql.JSONB, nullable=False),
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
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "undone_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_person_operations_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_person_operations_user_id",
        ),
        sa.CheckConstraint(
            "operation_type IN ('merge', 'split', 'rename', 'delete', 'confirm', 'reject')",
            name="ck_person_operations_type",
        ),
    )
    op.create_index(
        "ix_person_operations_workspace_created",
        "person_operations",
        ["workspace_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_person_operations_workspace_created",
        table_name="person_operations",
    )
    op.drop_table("person_operations")
