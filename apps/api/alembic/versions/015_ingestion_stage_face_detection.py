"""Allow FACE_DETECTION in ingestion_states.current_stage (S11-006).

Replaces the ``ck_ingestion_states_stage`` CHECK constraint with one that
includes the new FACE_DETECTION stage wedged between METADATA_EXTRACTED
and TEXT_EXTRACTED. Migration 002 baked the original 8-stage list into
the CHECK — we drop it and rebuild it with the 9-stage list so the
photo pipeline can persist the new transition.

No data rewrite needed: existing rows are all on the original 8 stages,
all of which are still accepted by the new constraint.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_STAGES = [
    "DISCOVERED",
    "FINGERPRINTED",
    "METADATA_EXTRACTED",
    "TEXT_EXTRACTED",
    "OCR_COMPLETED",
    "EMBEDDING_QUEUED",
    "EMBEDDED",
    "COMPLETED",
    # Terminal non-happy-path stages already accepted historically.
    "FAILED",
    "SKIPPED",
]

_NEW_STAGES = [
    "DISCOVERED",
    "FINGERPRINTED",
    "METADATA_EXTRACTED",
    "FACE_DETECTION",
    "TEXT_EXTRACTED",
    "OCR_COMPLETED",
    "EMBEDDING_QUEUED",
    "EMBEDDED",
    "COMPLETED",
    "FAILED",
    "SKIPPED",
]


def _in_clause(stages: list[str]) -> str:
    return ", ".join(f"'{s}'" for s in stages)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ingestion_states DROP CONSTRAINT ck_ingestion_states_stage"
    )
    op.execute(
        f"ALTER TABLE ingestion_states ADD CONSTRAINT ck_ingestion_states_stage "
        f"CHECK (current_stage IN ({_in_clause(_NEW_STAGES)}))"
    )


def downgrade() -> None:
    # Clear any rows sitting on the new stage before the old constraint
    # rejects them — downgrade implies rolling back the feature.
    op.execute(
        "UPDATE ingestion_states SET current_stage = 'METADATA_EXTRACTED' "
        "WHERE current_stage = 'FACE_DETECTION'"
    )
    op.execute(
        "ALTER TABLE ingestion_states DROP CONSTRAINT ck_ingestion_states_stage"
    )
    op.execute(
        f"ALTER TABLE ingestion_states ADD CONSTRAINT ck_ingestion_states_stage "
        f"CHECK (current_stage IN ({_in_clause(_OLD_STAGES)}))"
    )
