"""Add notifications table (G-09).

Revision ID: 011
Revises: 010
Create Date: 2026-04-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTIFICATION_TYPES = (
    "INGESTION_COMPLETE",
    "INGESTION_FAILED",
    "BACKUP_COMPLETE",
    "BACKUP_FAILED",
    "SYSTEM_DEGRADED",
    "SYSTEM_RECOVERED",
)


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("is_read", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"type IN ({', '.join(repr(t) for t in NOTIFICATION_TYPES)})",
            name="ck_notifications_type",
        ),
    )
    op.create_index("ix_notifications_user_workspace", "notifications", ["user_id", "workspace_id"])
    op.create_index("ix_notifications_unread", "notifications", ["user_id", "is_read", "created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
