"""correspondent_contact_candidates table — S07-004 People Graph bridge

Revision ID: 007
Revises: 006
Create Date: 2026-04-09

Design notes:
  - Stores fuzzy-match candidates between Paperless correspondents and
    EkamCore contacts, workspace-scoped.
  - UNIQUE(workspace_id, paperless_correspondent_id) ensures idempotent
    upserts: one candidate row per correspondent per workspace.
  - status: 'pending' | 'confirmed' | 'rejected' — reviewed via People Graph
    review queue (S12-001).
  - contact_id is nullable: a correspondent with no matching contact still
    gets a row (match_score=0, contact_id=NULL) so we know it was processed.
  - deleted_at for soft-delete per golden rules.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "correspondent_contact_candidates",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_uuid_v7()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("paperless_correspondent_id", sa.Integer, nullable=False),
        sa.Column("paperless_correspondent_name", sa.Text, nullable=False),
        sa.Column("contact_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("match_score", sa.Float, server_default="0.0", nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_ccc_workspace_id",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name="fk_ccc_contact_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "paperless_correspondent_id",
            name="uq_ccc_workspace_correspondent",
        ),
    )

    op.create_index(
        "ix_ccc_workspace_id",
        "correspondent_contact_candidates",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ccc_status",
        "correspondent_contact_candidates",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_ccc_contact_id",
        "correspondent_contact_candidates",
        ["contact_id"],
    )

    op.execute("""
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON correspondent_contact_candidates
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS set_updated_at ON correspondent_contact_candidates;"
    )
    op.drop_index("ix_ccc_contact_id", table_name="correspondent_contact_candidates")
    op.drop_index("ix_ccc_status", table_name="correspondent_contact_candidates")
    op.drop_index("ix_ccc_workspace_id", table_name="correspondent_contact_candidates")
    op.drop_table("correspondent_contact_candidates")
