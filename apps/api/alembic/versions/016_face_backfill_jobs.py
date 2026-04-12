"""Face backfill tracking — face_processed_at + face_backfill_jobs (S11-007).

Two changes:

1. Add ``photo_assets.face_processed_at TIMESTAMPTZ NULL`` so the backfill
   worker has an unambiguous "has this photo had face detection run
   against it?" marker. face_count can't serve this role because it
   defaults to 0 and is non-null — 0 is ambiguous between "never
   processed" and "processed, zero faces found". The new column is
   populated by ``process_photo_for_faces`` and cleared by
   ``hard_delete.delete_all_face_data`` so that consent revocation
   resets the backfill horizon as well.

2. Create ``face_backfill_jobs`` — a single row per backfill run,
   tracking progress and terminal state for the UI poller and cancel
   button. One row per (workspace, job); queries for "is anything
   running now?" filter on ``state='running'``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "photo_assets",
        sa.Column(
            "face_processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_photo_assets_face_processed_at",
        "photo_assets",
        ["workspace_id", "face_processed_at"],
    )

    op.create_table(
        "face_backfill_jobs",
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
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_photos", sa.Integer, nullable=False),
        sa.Column(
            "processed_photos",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "failed_photos",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(32),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text, nullable=True),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_face_backfill_jobs_workspace_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "state IN ('running', 'completed', 'failed', 'cancelled')",
            name="ck_face_backfill_jobs_state",
        ),
    )
    op.create_index(
        "ix_face_backfill_jobs_workspace",
        "face_backfill_jobs",
        ["workspace_id", "started_at"],
    )

    # set_updated_at trigger for housekeeping
    op.execute(
        """
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON face_backfill_jobs
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON face_backfill_jobs;")
    op.drop_index(
        "ix_face_backfill_jobs_workspace", table_name="face_backfill_jobs"
    )
    op.drop_table("face_backfill_jobs")
    op.drop_index(
        "ix_photo_assets_face_processed_at", table_name="photo_assets"
    )
    op.drop_column("photo_assets", "face_processed_at")
