"""object_audit_log table — append-only security audit trail

Revision ID: 006
Revises: 005
Create Date: 2026-03-29

Design notes:
  - BIGSERIAL pk (not UUID): high-volume append-only table; sequential IDs
    give free cursor-based pagination and efficient range scans.
  - No set_updated_at trigger: table is append-only by policy.
  - created_at / updated_at columns are inherited from the ORM Base and keep
    their server defaults (both = insert time); updated_at is intentionally
    never updated.
  - source_ip uses PostgreSQL INET type for compact network address storage.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "object_audit_log",
        sa.Column(
            "id",
            sa.BigInteger,
            primary_key=True,
            autoincrement=True,
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
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_state", postgresql.JSONB, nullable=True),
        sa.Column("new_state", postgresql.JSONB, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("source_ip", postgresql.INET, nullable=True),
        # No set_updated_at trigger — append-only
    )
    op.create_index("ix_audit_log_user_id", "object_audit_log", ["user_id"])
    op.create_index("ix_audit_log_workspace_id", "object_audit_log", ["workspace_id"])
    op.create_index("ix_audit_log_action", "object_audit_log", ["action"])
    op.create_index("ix_audit_log_created_at", "object_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="object_audit_log")
    op.drop_index("ix_audit_log_action", table_name="object_audit_log")
    op.drop_index("ix_audit_log_workspace_id", table_name="object_audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="object_audit_log")
    op.drop_table("object_audit_log")
