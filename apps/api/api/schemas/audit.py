from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    id: int
    timestamp: datetime  # exposed alias for created_at
    user_id: UUID | None
    workspace_id: UUID | None
    action: str
    object_type: str
    object_id: UUID | None
    old_state: dict | None
    new_state: dict | None
    metadata_json: dict | None
    source_ip: str | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: object) -> "AuditLogEntry":
        return cls(
            id=row.id,  # type: ignore[attr-defined]
            timestamp=row.created_at,  # type: ignore[attr-defined]
            user_id=row.user_id,  # type: ignore[attr-defined]
            workspace_id=row.workspace_id,  # type: ignore[attr-defined]
            action=row.action,  # type: ignore[attr-defined]
            object_type=row.object_type,  # type: ignore[attr-defined]
            object_id=row.object_id,  # type: ignore[attr-defined]
            old_state=row.old_state,  # type: ignore[attr-defined]
            new_state=row.new_state,  # type: ignore[attr-defined]
            metadata_json=row.metadata_json,  # type: ignore[attr-defined]
            source_ip=str(row.source_ip) if row.source_ip is not None else None,  # type: ignore[attr-defined]
        )


class AuditLogPage(BaseModel):
    items: list[AuditLogEntry]
    next_cursor: int | None = Field(default=None)
    total_in_page: int
