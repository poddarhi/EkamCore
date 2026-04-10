"""photo_assets table — S08-001 photo metadata store

Revision ID: 008
Revises: 007
Create Date: 2026-04-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "008"
down_revision: str = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photo_assets",
        sa.Column("id", sa.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("file_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gps_lat", sa.Float, nullable=True),
        sa.Column("gps_lon", sa.Float, nullable=True),
        sa.Column("location_name", sa.Text, nullable=True),
        sa.Column("camera_make", sa.Text, nullable=True),
        sa.Column("camera_model", sa.Text, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("orientation", sa.Integer, nullable=True),
        sa.Column("thumbnail_path", sa.Text, nullable=True),
        sa.Column("perceptual_hash", sa.String(16), nullable=True),
        sa.Column("exif_json", JSONB, nullable=True),
        sa.Column("face_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", name="uq_photo_assets_file_id"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_photo_assets_file_id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_photo_assets_workspace_id"),
    )
    op.create_index("ix_photo_assets_workspace_id", "photo_assets", ["workspace_id"])
    op.create_index("ix_photo_assets_taken_at", "photo_assets", ["workspace_id", "taken_at"])
    op.create_index("ix_photo_assets_location_name", "photo_assets", ["workspace_id", "location_name"])
    op.execute("""
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON photo_assets
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON photo_assets;")
    op.drop_index("ix_photo_assets_location_name", table_name="photo_assets")
    op.drop_index("ix_photo_assets_taken_at", table_name="photo_assets")
    op.drop_index("ix_photo_assets_workspace_id", table_name="photo_assets")
    op.drop_table("photo_assets")
