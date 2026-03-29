"""calendar_events table

Revision ID: 003
Revises: 002
Create Date: 2026-03-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_all_day", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("participants_json", postgresql.JSONB, nullable=True),
        sa.Column("recurrence_rule", sa.Text, nullable=True),
        sa.Column("calendar_name", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_calendar_events_workspace_id"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_calendar_events_source_id"),
        sa.UniqueConstraint("workspace_id", "source_id", "external_id", name="uq_calendar_events_ws_src_ext"),
    )
    op.create_index("ix_calendar_events_workspace_id", "calendar_events", ["workspace_id"])
    op.create_index("ix_calendar_events_source_id", "calendar_events", ["source_id"])
    op.create_index("ix_calendar_events_start_at", "calendar_events", ["start_at"])

    op.execute("""
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON calendar_events
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON calendar_events;")
    op.drop_index("ix_calendar_events_start_at", table_name="calendar_events")
    op.drop_index("ix_calendar_events_source_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_workspace_id", table_name="calendar_events")
    op.drop_table("calendar_events")
