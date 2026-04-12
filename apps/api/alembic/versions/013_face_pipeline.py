"""Phase 3 face pipeline: trusted_persons, face_clusters, face_detections (S11-001).

Revision ID: 013
Revises: 012
Create Date: 2026-04-11

Adds the three tables required for the face clustering and people graph
pipeline. pgcrypto was already enabled by migration 001 — we re-run
CREATE EXTENSION IF NOT EXISTS as a safety no-op so this migration can
be applied to any DB that somehow lacks it.

Table creation order (FK dependency): trusted_persons → face_clusters → face_detections

Encrypted columns (embedding_encrypted, centroid_encrypted) store
application-encrypted BYTEA produced by api.services.face.crypto.
The DB only sees opaque bytes.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safety: ensure pgcrypto is present. 001 already enabled it; this is idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── trusted_persons ─────────────────────────────────────────────────────
    op.create_table(
        "trusted_persons",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_uuid_v7()"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "canonical_contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trust_source", sa.String(32), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("merged_from_ids", postgresql.JSONB, nullable=True),
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
        sa.CheckConstraint(
            "trust_source IN ('contact_import', 'face_confirmed', 'manual', 'merged')",
            name="ck_trusted_persons_trust_source",
        ),
    )
    op.create_index("ix_trusted_persons_workspace", "trusted_persons", ["workspace_id"])

    # ── face_clusters ───────────────────────────────────────────────────────
    op.create_table(
        "face_clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_uuid_v7()"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("centroid_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("member_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "trusted_person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trusted_persons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "cluster_state",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'unconfirmed'"),
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
        sa.CheckConstraint(
            "cluster_state IN ('unconfirmed', 'confirmed', 'rejected', 'merged')",
            name="ck_face_clusters_cluster_state",
        ),
    )
    op.create_index("ix_face_clusters_workspace", "face_clusters", ["workspace_id"])
    op.create_index(
        "ix_face_clusters_trusted_person", "face_clusters", ["trusted_person_id"]
    )

    # ── face_detections ─────────────────────────────────────────────────────
    op.create_table(
        "face_detections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_uuid_v7()"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "photo_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("photo_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bbox_json", postgresql.JSONB, nullable=False),
        sa.Column("embedding_encrypted", sa.LargeBinary, nullable=False),
        sa.Column(
            "embedding_dim",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("512"),
        ),
        sa.Column("detector_version", sa.String(64), nullable=False),
        sa.Column("recognizer_version", sa.String(64), nullable=False),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("face_clusters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("detection_score", sa.Float, nullable=False),
        sa.Column(
            "qdrant_point_id",
            postgresql.UUID(as_uuid=True),
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
        sa.UniqueConstraint("qdrant_point_id", name="uq_face_detections_qdrant_point_id"),
    )
    op.create_index("ix_face_detections_workspace", "face_detections", ["workspace_id"])
    op.create_index(
        "ix_face_detections_photo_asset", "face_detections", ["photo_asset_id"]
    )
    op.create_index("ix_face_detections_cluster", "face_detections", ["cluster_id"])


def downgrade() -> None:
    # Drop in reverse FK order. Do NOT drop pgcrypto — 001 owns it.
    op.drop_index("ix_face_detections_cluster", table_name="face_detections")
    op.drop_index("ix_face_detections_photo_asset", table_name="face_detections")
    op.drop_index("ix_face_detections_workspace", table_name="face_detections")
    op.drop_table("face_detections")

    op.drop_index("ix_face_clusters_trusted_person", table_name="face_clusters")
    op.drop_index("ix_face_clusters_workspace", table_name="face_clusters")
    op.drop_table("face_clusters")

    op.drop_index("ix_trusted_persons_workspace", table_name="trusted_persons")
    op.drop_table("trusted_persons")
