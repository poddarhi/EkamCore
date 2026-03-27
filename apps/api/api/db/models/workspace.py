from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.models.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), server_default="personal", nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="workspaces_owned", lazy="selectin")
    members = relationship("WorkspaceMember", back_populates="workspace", lazy="selectin")
