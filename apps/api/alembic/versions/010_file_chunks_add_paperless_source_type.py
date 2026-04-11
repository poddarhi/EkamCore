"""Add 'paperless' to ck_file_chunks_source_type constraint (S07-002).

Revision ID: 010
Revises: 009
Create Date: 2026-04-11

The Paperless sync service stores chunks with source_type='paperless' to
distinguish them from local-file text/OCR chunks.  The original constraint
in migration 002 only allowed 'text' and 'ocr'.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TYPES = ("text", "ocr")
_NEW_TYPES = ("text", "ocr", "paperless")


def upgrade() -> None:
    op.drop_constraint("ck_file_chunks_source_type", "file_chunks", type_="check")
    op.create_check_constraint(
        "ck_file_chunks_source_type",
        "file_chunks",
        f"source_type IN ({', '.join(repr(t) for t in _NEW_TYPES)})",
    )


def downgrade() -> None:
    op.execute("DELETE FROM file_chunks WHERE source_type = 'paperless'")
    op.drop_constraint("ck_file_chunks_source_type", "file_chunks", type_="check")
    op.create_check_constraint(
        "ck_file_chunks_source_type",
        "file_chunks",
        f"source_type IN ({', '.join(repr(t) for t in _OLD_TYPES)})",
    )
