from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.models.base import Base


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), server_default="standard", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)

    workspaces_owned = relationship("Workspace", back_populates="owner", lazy="selectin")
    workspace_memberships = relationship("WorkspaceMember", back_populates="user", lazy="selectin")
    sessions = relationship("Session", back_populates="user", lazy="noload")
