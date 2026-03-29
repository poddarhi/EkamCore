"""Seed 15 sample contacts with varied completeness.

Finds (or creates) a contacts source on the admin workspace, then upserts
15 synthetic contacts directly via the service layer.

Usage:
    python -m scripts.seed_contacts
"""

import asyncio
from datetime import date

from sqlalchemy import select

from api.db.models.source import Source
from api.db.models.user import User
from api.db.models.workspace import Workspace
from api.db.session import async_session
from api.schemas.contact import ContactInput
from api.services.ingestion.contact_sync import upsert_contacts

ADMIN_EMAIL = "admin@ekamcore.dev"

_CONTACTS: list[ContactInput] = [
    # High-quality (name + email + phone) — eligible for TrustedPerson when Phase 3 lands
    ContactInput(
        external_id="seed-c-001",
        first_name="Alice",
        last_name="Chen",
        emails_json=["alice.chen@example.com", "alice@work.com"],
        phones_json=["+1-415-555-0101"],
        organization="Acme Corp",
        job_title="Senior Engineer",
        birthday=date(1988, 3, 14),
        notes="Met at PyCon 2024",
    ),
    ContactInput(
        external_id="seed-c-002",
        first_name="Bob",
        last_name="Martinez",
        emails_json=["bob.m@example.com"],
        phones_json=["+1-650-555-0102"],
        organization="Startup Inc",
        job_title="Product Manager",
    ),
    ContactInput(
        external_id="seed-c-003",
        first_name="Carol",
        last_name="Williams",
        emails_json=["carol.w@example.com"],
        phones_json=["+44-20-7946-0958"],
        organization="Global Ltd",
        job_title="Designer",
        birthday=date(1992, 11, 5),
    ),
    ContactInput(
        external_id="seed-c-004",
        first_name="David",
        last_name="Kim",
        emails_json=["dkim@example.com"],
        phones_json=["+1-212-555-0104"],
        addresses_json=[{"street": "123 Main St", "city": "New York", "country": "US"}],
        organization="Consulting LLC",
    ),
    ContactInput(
        external_id="seed-c-005",
        first_name="Eva",
        last_name="Kowalski",
        emails_json=["eva.k@example.com"],
        phones_json=["+48-22-555-0105"],
        organization="Tech GmbH",
        job_title="CTO",
        birthday=date(1985, 7, 22),
        notes="Conference keynote speaker",
    ),
    # Medium quality (name + email, no phone)
    ContactInput(
        external_id="seed-c-006",
        first_name="Frank",
        last_name="Okonkwo",
        emails_json=["frank.o@example.com"],
        organization="Lagos Ventures",
    ),
    ContactInput(
        external_id="seed-c-007",
        display_name="Grace Hopper Fan Club",
        emails_json=["newsletter@gracehopper.example.com"],
        notes="Mailing list",
    ),
    ContactInput(
        external_id="seed-c-008",
        first_name="Hiro",
        last_name="Nakamura",
        emails_json=["hiro@example.jp"],
        job_title="Architect",
        birthday=date(1990, 1, 1),
    ),
    # Name only (minimal quality)
    ContactInput(
        external_id="seed-c-009",
        first_name="Ivan",
        last_name="Petrov",
        organization="Unknown Co",
    ),
    ContactInput(
        external_id="seed-c-010",
        display_name="Mom",
        notes="Home phone in address book",
    ),
    # Phone only (no email)
    ContactInput(
        external_id="seed-c-011",
        first_name="Jane",
        last_name="Doe",
        phones_json=["+1-800-555-0111"],
    ),
    # Sparse / minimal data
    ContactInput(
        external_id="seed-c-012",
        display_name="Old Dentist Office",
        phones_json=["+1-555-0112"],
        notes="Dr. Smith's old number — may be outdated",
    ),
    ContactInput(
        external_id="seed-c-013",
        first_name="Kenji",
        last_name="Watanabe",
        emails_json=["k.watanabe@example.co.jp"],
        phones_json=["+81-3-555-0113"],
        addresses_json=[{"city": "Tokyo", "country": "JP"}],
        organization="Nippon Tech",
        job_title="Sales Director",
    ),
    ContactInput(
        external_id="seed-c-014",
        first_name="Lena",
        last_name="Müller",
        emails_json=["lena.m@example.de"],
        phones_json=["+49-30-555-0114"],
        birthday=date(1995, 9, 30),
        organization="Berlin Startup",
    ),
    ContactInput(
        external_id="seed-c-015",
        first_name="Marco",
        last_name="Rossi",
        emails_json=["marco.r@example.it"],
        phones_json=["+39-06-555-0115"],
        organization="Roma Agency",
        job_title="Creative Director",
        notes="Spoke at design summit",
    ),
]


async def seed() -> None:
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == ADMIN_EMAIL))).scalar_one_or_none()
        if not user:
            print(f"Admin user {ADMIN_EMAIL} not found. Run seed_admin.py first.")
            return

        workspace = (
            await db.execute(select(Workspace).where(Workspace.owner_id == user.id))
        ).scalars().first()
        if not workspace:
            print("No workspace found for admin.")
            return

        # Find or create a contacts source
        source = (
            await db.execute(
                select(Source).where(
                    Source.workspace_id == workspace.id,
                    Source.type == "contacts",
                    Source.deleted_at.is_(None),
                )
            )
        ).scalars().first()

        if not source:
            source = Source(
                workspace_id=workspace.id,
                name="Seed Contacts",
                type="contacts",
                registered_by=user.id,
                status="active",
            )
            db.add(source)
            await db.flush()
            print(f"Created contacts source: {source.id}")
        else:
            print(f"Using existing contacts source: {source.id}")

        inserted, updated, unchanged, tp_created = await upsert_contacts(
            source_id=source.id,
            workspace_id=workspace.id,
            contacts=_CONTACTS,
            db=db,
        )
        await db.commit()

    hq = sum(1 for c in _CONTACTS if (c.first_name or c.last_name or c.display_name) and c.emails_json and c.phones_json)
    print(
        f"Seeded {len(_CONTACTS)} contacts: {inserted} inserted, {updated} updated, {unchanged} unchanged."
    )
    print(f"  High-quality (eligible for TrustedPerson): {hq}")
    if tp_created:
        print(f"  TrustedPersons created: {tp_created}")


if __name__ == "__main__":
    asyncio.run(seed())
