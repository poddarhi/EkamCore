"""contacts table

Revision ID: 005
Revises: 004
Create Date: 2026-03-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(500), nullable=True),
        sa.Column("emails_json", postgresql.JSONB, nullable=True),
        sa.Column("phones_json", postgresql.JSONB, nullable=True),
        sa.Column("addresses_json", postgresql.JSONB, nullable=True),
        sa.Column("organization", sa.String(255), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("birthday", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_contacts_workspace_id"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_contacts_source_id"),
        sa.UniqueConstraint("workspace_id", "source_id", "external_id", name="uq_contacts_ws_src_ext"),
    )
    op.create_index("ix_contacts_workspace_id", "contacts", ["workspace_id"])
    op.create_index("ix_contacts_source_id", "contacts", ["source_id"])
    op.create_index("ix_contacts_workspace_display_name", "contacts", ["workspace_id", "display_name"])

    op.execute("""
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON contacts
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON contacts;")
    op.drop_index("ix_contacts_workspace_display_name", table_name="contacts")
    op.drop_index("ix_contacts_source_id", table_name="contacts")
    op.drop_index("ix_contacts_workspace_id", table_name="contacts")
    op.drop_table("contacts")
