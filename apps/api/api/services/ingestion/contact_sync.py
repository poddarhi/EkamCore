"""Contact import service: upsert by external_id with auto-TrustedPerson creation."""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.contact import Contact
from api.db.models.source import Source
from api.errors import NotFoundError, ValidationError
from api.schemas.contact import ContactInput

logger = structlog.get_logger()


def _is_high_quality(c: ContactInput) -> bool:
    """Return True if the contact has a name, at least one email, and at least one phone."""
    has_name = bool(c.first_name or c.last_name or c.display_name)
    has_email = bool(c.emails_json)
    has_phone = bool(c.phones_json)
    return has_name and has_email and has_phone


def _effective_display_name(c: ContactInput) -> str:
    """Derive a display name from available fields."""
    if c.display_name:
        return c.display_name
    parts = [p for p in (c.first_name, c.last_name) if p]
    return " ".join(parts) if parts else c.external_id


def _contact_changed(row: Contact, c: ContactInput) -> bool:
    """Return True if any mutable field differs between the stored row and the incoming contact."""
    if row.first_name != c.first_name:
        return True
    if row.last_name != c.last_name:
        return True
    if row.display_name != _effective_display_name(c):
        return True
    if row.emails_json != c.emails_json:
        return True
    if row.phones_json != c.phones_json:
        return True
    if row.addresses_json != c.addresses_json:
        return True
    if row.organization != c.organization:
        return True
    if row.job_title != c.job_title:
        return True
    if row.birthday != c.birthday:
        return True
    if row.notes != c.notes:
        return True
    return False


def _apply_contact(row: Contact, c: ContactInput) -> None:
    """Overwrite mutable fields on an existing row from the incoming contact."""
    row.first_name = c.first_name
    row.last_name = c.last_name
    row.display_name = c.display_name
    row.emails_json = c.emails_json
    row.phones_json = c.phones_json
    row.addresses_json = c.addresses_json
    row.organization = c.organization
    row.job_title = c.job_title
    row.birthday = c.birthday
    row.notes = c.notes


async def _trusted_persons_table_exists(db: AsyncSession) -> bool:
    """Check if the trusted_persons table has been created (Phase 3 feature gate)."""
    result = await db.execute(text("SELECT to_regclass('public.trusted_persons')"))
    return result.scalar() is not None


async def _create_trusted_person(
    db: AsyncSession,
    workspace_id: UUID,
    contact: Contact,
    display_name: str,
    confirmed_by: UUID,
) -> None:
    """Insert a TrustedPerson row via raw SQL (model lives in Phase 3)."""
    await db.execute(
        text("""
            INSERT INTO trusted_persons (
                id, workspace_id, display_name, canonical_contact_id,
                trust_source, confirmed_at, confirmed_by,
                created_at, updated_at
            ) VALUES (
                gen_uuid_v7(), :workspace_id, :display_name, :canonical_contact_id,
                'contact_import', now(), :confirmed_by,
                now(), now()
            )
        """),
        {
            "workspace_id": str(workspace_id),
            "display_name": display_name,
            "canonical_contact_id": str(contact.id),
            "confirmed_by": str(confirmed_by),
        },
    )


async def upsert_contacts(
    source_id: UUID,
    workspace_id: UUID,
    contacts: list[ContactInput],
    db: AsyncSession,
) -> tuple[int, int, int, int]:
    """Upsert contacts for a source.

    Returns (inserted, updated, unchanged, trusted_persons_created).

    Validates that source_id belongs to workspace_id.
    Deduplicates incoming contacts by external_id (last occurrence wins).
    For newly-inserted high-quality contacts (name + email + phone), creates a
    TrustedPerson record if the trusted_persons table exists (Phase 3 feature).
    Updates source.last_sync_at on completion.
    """
    # Validate source ownership
    source_stmt = select(Source).where(
        Source.id == source_id,
        Source.workspace_id == workspace_id,
        Source.deleted_at.is_(None),
    )
    source = (await db.execute(source_stmt)).scalar_one_or_none()
    if not source:
        raise NotFoundError(error_code="SOURCE_NOT_FOUND", message="Source not found for this workspace.")

    if source.type != "contacts":
        raise ValidationError(
            error_code="SOURCE_TYPE_MISMATCH",
            message=f"Expected source type 'contacts', got '{source.type}'.",
        )

    # Deduplicate incoming contacts by external_id (last occurrence wins)
    deduped: dict[str, ContactInput] = {}
    for c in contacts:
        deduped[c.external_id] = c

    now = datetime.now(timezone.utc)

    if not deduped:
        source.last_sync_at = now
        await db.flush()
        return 0, 0, 0, 0

    # Load existing contacts for this source
    existing_stmt = select(Contact).where(
        Contact.source_id == source_id,
        Contact.workspace_id == workspace_id,
        Contact.deleted_at.is_(None),
    )
    existing: dict[str, Contact] = {
        row.external_id: row
        for row in (await db.execute(existing_stmt)).scalars().all()
    }

    # Check trusted_persons table once (Phase 3 gate)
    tp_table_exists = await _trusted_persons_table_exists(db)

    inserted = updated = unchanged = trusted_persons_created = 0
    new_hq_contacts: list[tuple[Contact, str]] = []  # (contact_row, display_name)

    for external_id, c in deduped.items():
        if external_id not in existing:
            display_name = _effective_display_name(c)
            row = Contact(
                workspace_id=workspace_id,
                source_id=source_id,
                external_id=external_id,
                first_name=c.first_name,
                last_name=c.last_name,
                display_name=display_name,
                emails_json=c.emails_json,
                phones_json=c.phones_json,
                addresses_json=c.addresses_json,
                organization=c.organization,
                job_title=c.job_title,
                birthday=c.birthday,
                notes=c.notes,
                imported_at=now,
                last_synced_at=now,
            )
            db.add(row)
            inserted += 1
            if tp_table_exists and _is_high_quality(c):
                new_hq_contacts.append((row, display_name))
        else:
            row = existing[external_id]
            row.last_synced_at = now
            if _contact_changed(row, c):
                _apply_contact(row, c)
                if not row.display_name:
                    row.display_name = _effective_display_name(c)
                updated += 1
            else:
                unchanged += 1

    # Flush to get IDs for newly inserted contacts before creating TrustedPersons
    await db.flush()

    for contact_row, display_name in new_hq_contacts:
        await _create_trusted_person(
            db=db,
            workspace_id=workspace_id,
            contact=contact_row,
            display_name=display_name,
            confirmed_by=source.registered_by,
        )
        trusted_persons_created += 1

    source.last_sync_at = now
    await db.flush()

    logger.info(
        "contacts_upserted",
        source_id=str(source_id),
        workspace_id=str(workspace_id),
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        trusted_persons_created=trusted_persons_created,
    )
    return inserted, updated, unchanged, trusted_persons_created
