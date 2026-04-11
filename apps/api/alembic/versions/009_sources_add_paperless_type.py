"""Add 'paperless' to ck_sources_type constraint (S07-001 / S07-002).

Revision ID: 009
Revises: 008
Create Date: 2026-04-11

The Paperless sync service (sync.py) auto-creates a source row with
type='paperless' on first sync.  The original constraint in migration 002
only covered local_folder, photo_folder, contacts, calendar, reminders.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Original types (migration 002)
_OLD_TYPES = ("local_folder", "photo_folder", "contacts", "calendar", "reminders")
# Extended types (this migration)
_NEW_TYPES = ("local_folder", "photo_folder", "contacts", "calendar", "reminders", "paperless")


def upgrade() -> None:
    # PostgreSQL CHECK constraints must be dropped and re-created to change them.
    op.drop_constraint("ck_sources_type", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_type",
        "sources",
        f"type IN ({', '.join(repr(t) for t in _NEW_TYPES)})",
    )


def downgrade() -> None:
    # Remove any 'paperless' rows first to avoid violating the old constraint.
    op.execute("DELETE FROM sources WHERE type = 'paperless'")
    op.drop_constraint("ck_sources_type", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_type",
        "sources",
        f"type IN ({', '.join(repr(t) for t in _OLD_TYPES)})",
    )
