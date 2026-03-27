from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", "namespace", "key",
            name="uq_settings_ws_user_ns_key",
        ),
    )

    workspace_id: Mapped[UUID | None] = mapped_column(ForeignKey("workspaces.id"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    namespace: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_json: Mapped[dict | None] = mapped_column(JSONB)
