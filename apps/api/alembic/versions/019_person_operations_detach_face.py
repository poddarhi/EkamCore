"""Extend person_operations.operation_type CHECK to include 'detach_face' — S13-003.

The remove-face flow on the Person detail page records a
``detach_face`` row in the undo log so users can reverse a
mistaken correction. Migration 018's CHECK constraint did not
allow the new value; this migration drops and re-creates it.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_person_operations_type",
        "person_operations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_person_operations_type",
        "person_operations",
        "operation_type IN ('merge', 'split', 'rename', 'delete', "
        "'confirm', 'reject', 'detach_face')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_person_operations_type",
        "person_operations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_person_operations_type",
        "person_operations",
        "operation_type IN ('merge', 'split', 'rename', 'delete', "
        "'confirm', 'reject')",
    )
