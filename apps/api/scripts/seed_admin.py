"""Seed a default admin user for development.

Usage: python -m scripts.seed_admin
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.models.workspace_member import WorkspaceMember
from api.db.session import async_session
from api.services.auth import hash_password

ADMIN_EMAIL = "admin@ekamcore.dev"
ADMIN_PASSWORD = "admin123"


async def seed() -> None:
    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        if result.scalar_one_or_none():
            print(f"Admin user {ADMIN_EMAIL} already exists, skipping.")
            return

        user = User(
            email=ADMIN_EMAIL,
            display_name="Admin",
            password_hash=hash_password(ADMIN_PASSWORD),
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        workspace = Workspace(
            name="Personal",
            type="personal",
            owner_id=user.id,
        )
        db.add(workspace)
        await db.flush()

        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="admin",
        )
        db.add(member)

        await db.commit()
        print(f"Created admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print(f"Created workspace: {workspace.name} (id={workspace.id})")


if __name__ == "__main__":
    asyncio.run(seed())
