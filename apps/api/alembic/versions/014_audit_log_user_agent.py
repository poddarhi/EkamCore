"""Add user_agent column to object_audit_log for biometric consent trail (S11-002).

Revision ID: 014
Revises: 013
Create Date: 2026-04-12

ART-15 §3 requires that biometric consent events record the user agent
string alongside IP, user_id, and timestamp. This migration adds the
column as nullable so existing audit rows remain valid.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "object_audit_log",
        sa.Column("user_agent", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("object_audit_log", "user_agent")
