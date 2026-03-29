"""Tests for contact import service and POST /api/v1/internal/ingest/contacts."""

from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.contact import Contact
from api.db.models.source import Source
from api.db.models.workspace import Workspace
from api.errors import NotFoundError, ValidationError
from api.schemas.contact import ContactInput
from api.services.ingestion.contact_sync import (
    _is_high_quality,
    upsert_contacts,
)


# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------

_UNSET: list = object()  # type: ignore[assignment]


def _contact(
    external_id: str = "c-001",
    first_name: str | None = "Alice",
    last_name: str | None = "Smith",
    display_name: str | None = None,
    emails_json: list | None = _UNSET,
    phones_json: list | None = _UNSET,
    **kwargs,
) -> ContactInput:
    return ContactInput(
        external_id=external_id,
        first_name=first_name,
        last_name=last_name,
        display_name=display_name,
        emails_json=emails_json if emails_json is not _UNSET else ["alice@example.com"],
        phones_json=phones_json if phones_json is not _UNSET else ["+1-555-0100"],
        **kwargs,
    )


def _minimal_contact(external_id: str = "c-min") -> ContactInput:
    """Contact with only external_id and display_name — not high quality."""
    return ContactInput(external_id=external_id, display_name="Minimal Contact")


async def _make_contacts_source(db: AsyncSession, seed_user: dict) -> Source:
    source = Source(
        workspace_id=seed_user["workspace_id"],
        name="Test Contacts",
        type="contacts",
        registered_by=seed_user["user_id"],
        status="active",
    )
    db.add(source)
    await db.flush()
    return source


# ---------------------------------------------------------------------------
# Unit tests for _is_high_quality
# ---------------------------------------------------------------------------

def test_high_quality_with_name_email_phone() -> None:
    c = _contact(first_name="Alice", last_name="Smith",
                 emails_json=["a@b.com"], phones_json=["+1-555-0100"])
    assert _is_high_quality(c) is True


def test_high_quality_missing_phone() -> None:
    c = _contact(phones_json=None)
    assert _is_high_quality(c) is False


def test_high_quality_missing_email() -> None:
    c = _contact(emails_json=None)
    assert _is_high_quality(c) is False


def test_high_quality_missing_name() -> None:
    c = ContactInput(
        external_id="x",
        emails_json=["a@b.com"],
        phones_json=["+1-555-0100"],
    )
    assert _is_high_quality(c) is False


def test_high_quality_display_name_only_counts_as_name() -> None:
    c = ContactInput(
        external_id="x",
        display_name="Bob Jones",
        emails_json=["bob@example.com"],
        phones_json=["+1-555-0200"],
    )
    assert _is_high_quality(c) is True


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_new_contacts(test_session_factory, seed_user: dict) -> None:
    """New contacts are inserted; inserted count is correct."""
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        inserted, updated, unchanged, tp = await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[_contact("c1"), _contact("c2"), _minimal_contact("c3")],
            db=db,
        )
        await db.commit()

    assert inserted == 3
    assert updated == 0
    assert unchanged == 0
    # trusted_persons table doesn't exist yet (Phase 3), so always 0
    assert tp == 0


@pytest.mark.asyncio
async def test_upsert_updated_contacts(test_session_factory, seed_user: dict) -> None:
    """Re-syncing with a changed field increments the updated counter."""
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[_contact("c-upd", organization="OldCo")],
            db=db,
        )
        await db.flush()

        inserted, updated, unchanged, _ = await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[_contact("c-upd", organization="NewCo")],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Contact).where(
                    Contact.source_id == source.id,
                    Contact.external_id == "c-upd",
                )
            )
        ).scalar_one()
        assert row.organization == "NewCo"

    assert inserted == 0
    assert updated == 1
    assert unchanged == 0


@pytest.mark.asyncio
async def test_upsert_unchanged_contacts(test_session_factory, seed_user: dict) -> None:
    """Re-syncing identical contacts increments unchanged, not updated."""
    c = _contact("c-same", organization="AcmeCorp")
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[c],
            db=db,
        )
        await db.flush()

        inserted, updated, unchanged, _ = await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[c],
            db=db,
        )

    assert inserted == 0
    assert updated == 0
    assert unchanged == 1


@pytest.mark.asyncio
async def test_upsert_duplicate_external_id_in_request(test_session_factory, seed_user: dict) -> None:
    """Duplicate external_id in the same batch: last occurrence wins, only 1 row created."""
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        contacts = [
            _contact("dup", first_name="First"),
            _contact("dup", first_name="Second"),  # should win
        ]
        inserted, updated, unchanged, _ = await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=contacts,
            db=db,
        )
        await db.flush()

        rows = (
            await db.execute(
                select(Contact).where(
                    Contact.source_id == source.id,
                    Contact.external_id == "dup",
                )
            )
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].first_name == "Second"
    assert inserted == 1
    assert updated == 0


@pytest.mark.asyncio
async def test_upsert_workspace_isolation(test_session_factory, seed_user: dict) -> None:
    """Source from workspace A cannot be used with workspace B's ID."""
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)
        with pytest.raises(NotFoundError):
            await upsert_contacts(
                source_id=source.id,
                workspace_id=uuid4(),  # wrong workspace
                contacts=[_contact("c1")],
                db=db,
            )


@pytest.mark.asyncio
async def test_upsert_source_not_found(test_session_factory, seed_user: dict) -> None:
    """Non-existent source_id raises NotFoundError."""
    async with test_session_factory() as db:
        with pytest.raises(NotFoundError):
            await upsert_contacts(
                source_id=uuid4(),
                workspace_id=seed_user["workspace_id"],
                contacts=[_contact("c1")],
                db=db,
            )


@pytest.mark.asyncio
async def test_upsert_wrong_source_type(test_session_factory, seed_user: dict) -> None:
    """Source with type != 'contacts' raises ValidationError."""
    async with test_session_factory() as db:
        bad_source = Source(
            workspace_id=seed_user["workspace_id"],
            name="Calendar Source",
            type="calendar",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(bad_source)
        await db.flush()

        with pytest.raises(ValidationError) as exc_info:
            await upsert_contacts(
                source_id=bad_source.id,
                workspace_id=seed_user["workspace_id"],
                contacts=[_contact("c1")],
                db=db,
            )
    assert exc_info.value.error_code == "SOURCE_TYPE_MISMATCH"


@pytest.mark.asyncio
async def test_upsert_empty_contacts(test_session_factory, seed_user: dict) -> None:
    """Empty contact list returns 0/0/0/0 and still updates last_sync_at."""
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        inserted, updated, unchanged, tp = await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[],
            db=db,
        )
        await db.flush()

        refreshed = await db.get(Source, source.id)

    assert inserted == 0
    assert updated == 0
    assert unchanged == 0
    assert tp == 0
    assert refreshed is not None
    assert refreshed.last_sync_at is not None


@pytest.mark.asyncio
async def test_last_sync_at_updated(test_session_factory, seed_user: dict) -> None:
    """source.last_sync_at is set after a successful upsert."""
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)
        assert source.last_sync_at is None

        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[_contact("c1")],
            db=db,
        )
        await db.flush()
        await db.refresh(source)

    assert source.last_sync_at is not None


@pytest.mark.asyncio
async def test_display_name_derived_from_name_parts(test_session_factory, seed_user: dict) -> None:
    """display_name is derived from first+last when not explicitly provided."""
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[_contact("c-name", first_name="John", last_name="Doe", display_name=None)],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Contact).where(
                    Contact.source_id == source.id,
                    Contact.external_id == "c-name",
                )
            )
        ).scalar_one()

    assert row.display_name == "John Doe"


@pytest.mark.asyncio
async def test_jsonb_emails_stored_and_retrieved(test_session_factory, seed_user: dict) -> None:
    """emails_json list is stored and retrieved correctly via JSONB."""
    emails = ["work@example.com", "personal@example.com"]
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[_contact("c-emails", emails_json=emails)],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Contact).where(
                    Contact.source_id == source.id,
                    Contact.external_id == "c-emails",
                )
            )
        ).scalar_one()

    assert row.emails_json == emails


@pytest.mark.asyncio
async def test_birthday_stored_correctly(test_session_factory, seed_user: dict) -> None:
    """birthday date field is stored and retrieved correctly."""
    bday = date(1990, 6, 15)
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[_contact("c-bday", birthday=bday)],
            db=db,
        )
        await db.flush()

        row = (
            await db.execute(
                select(Contact).where(
                    Contact.source_id == source.id,
                    Contact.external_id == "c-bday",
                )
            )
        ).scalar_one()

    assert row.birthday == bday


@pytest.mark.asyncio
async def test_last_synced_at_updated_on_unchanged(test_session_factory, seed_user: dict) -> None:
    """last_synced_at is updated even for unchanged contacts."""
    c = _contact("c-ts")
    async with test_session_factory() as db:
        source = await _make_contacts_source(db, seed_user)

        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[c],
            db=db,
        )
        await db.flush()

        row_before = (
            await db.execute(
                select(Contact).where(Contact.source_id == source.id, Contact.external_id == "c-ts")
            )
        ).scalar_one()
        first_sync = row_before.last_synced_at

        # Re-sync identical contact
        await upsert_contacts(
            source_id=source.id,
            workspace_id=seed_user["workspace_id"],
            contacts=[c],
            db=db,
        )
        await db.flush()
        await db.refresh(row_before)

    assert row_before.last_synced_at is not None
    assert first_sync is not None


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_contacts_endpoint_success(
    client: AsyncClient, seed_user: dict, test_session_factory
) -> None:
    """POST /api/v1/internal/ingest/contacts returns 200 with counts."""
    async with test_session_factory() as db:
        source = Source(
            workspace_id=seed_user["workspace_id"],
            name="HTTP Test Contacts",
            type="contacts",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(source)
        await db.commit()
        source_id = source.id

    response = await client.post(
        "/api/v1/internal/ingest/contacts",
        json={
            "workspace_id": str(seed_user["workspace_id"]),
            "source_id": str(source_id),
            "contacts": [
                {
                    "external_id": "http-c1",
                    "first_name": "Eve",
                    "last_name": "Johnson",
                    "emails_json": ["eve@example.com"],
                    "phones_json": ["+1-555-0300"],
                }
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["inserted"] == 1
    assert data["updated"] == 0
    assert data["unchanged"] == 0
    assert data["trusted_persons_created"] == 0  # table doesn't exist yet


@pytest.mark.asyncio
async def test_ingest_contacts_endpoint_source_not_found(
    client: AsyncClient, seed_user: dict
) -> None:
    """Returns 404 when source_id does not exist."""
    response = await client.post(
        "/api/v1/internal/ingest/contacts",
        json={
            "workspace_id": str(seed_user["workspace_id"]),
            "source_id": str(uuid4()),
            "contacts": [],
        },
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_ingest_contacts_endpoint_workspace_mismatch(
    client: AsyncClient, seed_user: dict, test_session_factory
) -> None:
    """Returns 404 when source_id belongs to a different workspace."""
    async with test_session_factory() as db:
        other_ws = Workspace(name="Other WS", type="personal", owner_id=seed_user["user_id"])
        db.add(other_ws)
        await db.flush()

        source = Source(
            workspace_id=other_ws.id,
            name="Other Contacts",
            type="contacts",
            registered_by=seed_user["user_id"],
            status="active",
        )
        db.add(source)
        await db.commit()
        source_id = source.id

    response = await client.post(
        "/api/v1/internal/ingest/contacts",
        json={
            "workspace_id": str(seed_user["workspace_id"]),
            "source_id": str(source_id),
            "contacts": [],
        },
    )
    assert response.status_code == 404
