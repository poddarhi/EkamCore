from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models.

    Provides id (UUID v7), created_at, and updated_at columns.
    The updated_at column is maintained by a DB trigger (set_updated_at).
    """

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_uuid_v7()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
    )
