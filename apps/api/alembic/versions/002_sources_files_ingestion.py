"""Sources, files, file_chunks, and ingestion_states tables

Revision ID: 002
Revises: 001
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum values
SOURCE_TYPES = ("local_folder", "photo_folder", "contacts", "calendar", "reminders")
SOURCE_STATUSES = ("active", "paused", "error")
CHUNK_SOURCE_TYPES = ("text", "ocr")
PIPELINE_STAGES = (
    "DISCOVERED",
    "FINGERPRINTED",
    "METADATA_EXTRACTED",
    "TEXT_EXTRACTED",
    "OCR_COMPLETED",
    "EMBEDDING_QUEUED",
    "EMBEDDED",
    "COMPLETED",
    "FAILED",
    "SKIPPED",
)


def upgrade() -> None:
    # ── sources ──
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("path", sa.Text, nullable=True),
        sa.Column("config_json", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_sources_workspace_id"),
        sa.ForeignKeyConstraint(["registered_by"], ["users.id"], name="fk_sources_registered_by"),
        sa.CheckConstraint(
            f"type IN ({', '.join(repr(t) for t in SOURCE_TYPES)})",
            name="ck_sources_type",
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in SOURCE_STATUSES)})",
            name="ck_sources_status",
        ),
    )
    op.create_index("ix_sources_workspace_id", "sources", ["workspace_id"])

    # ── files ──
    op.create_table(
        "files",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("content_hash_sha256", sa.CHAR(64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("is_duplicate", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("duplicate_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_files_workspace_id"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_files_source_id"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["files.id"], name="fk_files_duplicate_of_id"),
    )
    op.create_index("ix_files_workspace_id", "files", ["workspace_id"])
    op.create_index("ix_files_source_id", "files", ["source_id"])
    op.create_index("ix_files_content_hash", "files", ["content_hash_sha256"])

    # ── file_chunks ──
    op.create_table(
        "file_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text_content", sa.Text, nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("source_type", sa.String(10), nullable=False),
        sa.Column("embedding_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_file_chunks_file_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_file_chunks_workspace_id"),
        sa.UniqueConstraint("file_id", "chunk_index", name="uq_file_chunks_file_chunk_idx"),
        sa.CheckConstraint(
            f"source_type IN ({', '.join(repr(t) for t in CHUNK_SOURCE_TYPES)})",
            name="ck_file_chunks_source_type",
        ),
    )

    # ── ingestion_states ──
    op.create_table(
        "ingestion_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_stage", sa.String(30), server_default="DISCOVERED", nullable=False),
        sa.Column("stages_completed", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_ingestion_states_file_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_ingestion_states_workspace_id"),
        sa.UniqueConstraint("file_id", name="uq_ingestion_states_file_id"),
        sa.CheckConstraint(
            f"current_stage IN ({', '.join(repr(s) for s in PIPELINE_STAGES)})",
            name="ck_ingestion_states_stage",
        ),
        sa.CheckConstraint("retry_count >= 0 AND retry_count <= 3", name="ck_ingestion_states_retry"),
    )

    # Apply set_updated_at trigger to new tables
    for table in ["sources", "files", "file_chunks", "ingestion_states"]:
        op.execute(f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """)


def downgrade() -> None:
    for table in ["ingestion_states", "file_chunks", "files", "sources"]:
        op.execute(f"DROP TRIGGER IF EXISTS set_updated_at ON {table};")

    op.drop_table("ingestion_states")
    op.drop_table("file_chunks")
    op.drop_table("files")
    op.drop_table("sources")
