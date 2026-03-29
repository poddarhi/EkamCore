"""reminders table

Revision ID: 004
Revises: 003
Create Date: 2026-03-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_completed", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("priority", sa.String(10), server_default="none", nullable=False),
        sa.Column("list_name", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("write_through_status", sa.String(10), server_default="pending", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_reminders_workspace_id"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_reminders_source_id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_reminders_created_by"),
        sa.CheckConstraint("priority IN ('high', 'medium', 'low', 'none')", name="ck_reminders_priority"),
        sa.CheckConstraint(
            "write_through_status IN ('pending', 'success', 'failed')",
            name="ck_reminders_write_through_status",
        ),
    )
    op.create_index("ix_reminders_workspace_id", "reminders", ["workspace_id"])
    op.create_index("ix_reminders_source_id", "reminders", ["source_id"])
    # Partial index for upcoming reminders lookup
    op.create_index(
        "ix_reminders_workspace_due_at",
        "reminders",
        ["workspace_id", "due_at"],
        postgresql_where=sa.text("completed_at IS NULL"),
    )
    # Partial unique index for import deduplication
    op.create_index(
        "uq_reminders_ws_src_ext",
        "reminders",
        ["workspace_id", "source_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL AND external_id IS NOT NULL AND deleted_at IS NULL"),
    )

    op.execute("""
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON reminders
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON reminders;")
    op.drop_index("uq_reminders_ws_src_ext", table_name="reminders")
    op.drop_index("ix_reminders_workspace_due_at", table_name="reminders")
    op.drop_index("ix_reminders_source_id", table_name="reminders")
    op.drop_index("ix_reminders_workspace_id", table_name="reminders")
    op.drop_table("reminders")
