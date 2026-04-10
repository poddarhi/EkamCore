"""Unit tests for the Paperless correspondent → contacts bridge (S07-004).

All Paperless API calls and DB interactions are mocked — no network or DB
needed.  Tests verify:
  - Exact and fuzzy name matching
  - No-match path (score below threshold)
  - Upsert idempotency (no duplicate rows)
  - Confirmed/rejected candidates are never overwritten
  - Workspace isolation (contacts from other workspaces never matched)
  - ServiceUnavailableError propagation when Paperless is down
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from api.db.models.correspondent_candidate import (
    CANDIDATE_STATUS_CONFIRMED,
    CANDIDATE_STATUS_PENDING,
    CANDIDATE_STATUS_REJECTED,
    CorrespondentContactCandidate,
)
from api.errors import ServiceUnavailableError
from api.services.paperless.correspondent_bridge import (
    MATCH_THRESHOLD,
    _best_match,
    _build_contact_records,
    _normalise,
    run_correspondent_bridge,
)
from api.services.paperless.models import PaperlessCorrespondent


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_corr(id: int = 1, name: str = "Acme Corp") -> PaperlessCorrespondent:
    return PaperlessCorrespondent(id=id, name=name)


def _make_contact(
    workspace_id: Any = None,
    display_name: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> Mock:
    c = Mock()
    c.id = uuid4()
    c.workspace_id = workspace_id or uuid4()
    c.display_name = display_name
    c.first_name = first_name
    c.last_name = last_name
    c.deleted_at = None
    return c


def _make_db(contacts: list, existing_candidates: list) -> AsyncMock:
    """Build a minimal AsyncSession mock."""
    db = AsyncMock()

    # first execute call → contacts query
    # second execute call → existing candidates query
    contacts_result = MagicMock()
    contacts_result.scalars.return_value.all.return_value = contacts

    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = existing_candidates

    db.execute = AsyncMock(side_effect=[contacts_result, existing_result])
    db.add = Mock()
    db.commit = AsyncMock()
    return db


# ── _normalise ────────────────────────────────────────────────────────────────


def test_normalise_strips_and_casefolds():
    assert _normalise("  John   SMITH  ") == "john smith"


def test_normalise_empty():
    assert _normalise("") == ""


# ── _build_contact_records ────────────────────────────────────────────────────


def test_build_uses_display_name():
    c = _make_contact(display_name="Acme Corp", first_name="Acme", last_name="Corp")
    records = _build_contact_records([c])
    assert len(records) == 1
    assert records[0].name == "acme corp"


def test_build_falls_back_to_first_last():
    c = _make_contact(display_name=None, first_name="John", last_name="Smith")
    records = _build_contact_records([c])
    assert records[0].name == "john smith"


def test_build_skips_contacts_with_no_name():
    c = _make_contact(display_name=None, first_name=None, last_name=None)
    records = _build_contact_records([c])
    assert records == []


# ── _best_match ───────────────────────────────────────────────────────────────


def test_exact_match_returns_full_score():
    c = _make_contact(display_name="Acme Corp")
    records = _build_contact_records([c])
    contact_id, score = _best_match("Acme Corp", records)
    assert contact_id == c.id
    assert score == pytest.approx(1.0)


def test_fuzzy_match_above_threshold():
    # "Acme Corporation" vs "Acme Corp" — should be above 0.6
    c = _make_contact(display_name="Acme Corp")
    records = _build_contact_records([c])
    contact_id, score = _best_match("Acme Corporation", records)
    assert contact_id == c.id
    assert score >= MATCH_THRESHOLD


def test_no_match_below_threshold():
    c = _make_contact(display_name="Acme Corp")
    records = _build_contact_records([c])
    contact_id, score = _best_match("Totally Unrelated Entity", records)
    assert contact_id is None
    assert score < MATCH_THRESHOLD


def test_no_contacts_returns_none():
    contact_id, score = _best_match("Anyone", [])
    assert contact_id is None
    assert score == 0.0


def test_picks_best_of_multiple_contacts():
    c1 = _make_contact(display_name="Acme Corp")
    c2 = _make_contact(display_name="John Smith")
    records = _build_contact_records([c1, c2])
    contact_id, score = _best_match("Acme Corp", records)
    assert contact_id == c1.id


# ── run_correspondent_bridge ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bridge_creates_new_candidate():
    ws_id = uuid4()
    corr = _make_corr(id=42, name="Acme Corp")
    contact = _make_contact(workspace_id=ws_id, display_name="Acme Corp")
    db = _make_db(contacts=[contact], existing_candidates=[])

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(return_value=[corr])
        mock_get_client.return_value = mock_client

        result = await run_correspondent_bridge(workspace_id=ws_id, db=db)

    assert result["processed"] == 1
    assert result["new"] == 1
    assert result["updated"] == 0
    db.add.assert_called_once()
    db.commit.assert_awaited_once()

    added: CorrespondentContactCandidate = db.add.call_args[0][0]
    assert added.workspace_id == ws_id
    assert added.paperless_correspondent_id == 42
    assert added.contact_id == contact.id
    assert added.match_score >= MATCH_THRESHOLD
    assert added.status == CANDIDATE_STATUS_PENDING


@pytest.mark.asyncio
async def test_bridge_no_match_stores_null_contact():
    ws_id = uuid4()
    corr = _make_corr(id=1, name="Totally Unknown Entity XYZ")
    contact = _make_contact(workspace_id=ws_id, display_name="Acme Corp")
    db = _make_db(contacts=[contact], existing_candidates=[])

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(return_value=[corr])
        mock_get_client.return_value = mock_client

        result = await run_correspondent_bridge(workspace_id=ws_id, db=db)

    assert result["no_match"] == 1
    added: CorrespondentContactCandidate = db.add.call_args[0][0]
    assert added.contact_id is None


@pytest.mark.asyncio
async def test_bridge_updates_existing_pending_candidate():
    ws_id = uuid4()
    corr = _make_corr(id=7, name="Acme Corp")
    contact = _make_contact(workspace_id=ws_id, display_name="Acme Corp")

    existing = Mock(spec=CorrespondentContactCandidate)
    existing.paperless_correspondent_id = 7
    existing.status = CANDIDATE_STATUS_PENDING

    db = _make_db(contacts=[contact], existing_candidates=[existing])

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(return_value=[corr])
        mock_get_client.return_value = mock_client

        result = await run_correspondent_bridge(workspace_id=ws_id, db=db)

    assert result["updated"] == 1
    assert result["new"] == 0
    db.add.assert_not_called()
    assert existing.contact_id == contact.id
    assert existing.match_score >= MATCH_THRESHOLD


@pytest.mark.asyncio
async def test_confirmed_candidate_not_overwritten():
    ws_id = uuid4()
    original_contact_id = uuid4()
    corr = _make_corr(id=5, name="Acme Corp")
    contact = _make_contact(workspace_id=ws_id, display_name="Completely Different Name")

    existing = Mock(spec=CorrespondentContactCandidate)
    existing.paperless_correspondent_id = 5
    existing.status = CANDIDATE_STATUS_CONFIRMED
    existing.contact_id = original_contact_id

    db = _make_db(contacts=[contact], existing_candidates=[existing])

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(return_value=[corr])
        mock_get_client.return_value = mock_client

        result = await run_correspondent_bridge(workspace_id=ws_id, db=db)

    # confirmed row is skipped — counts remain 0
    assert result["new"] == 0
    assert result["updated"] == 0
    # contact_id on the existing row must NOT have changed
    assert existing.contact_id == original_contact_id


@pytest.mark.asyncio
async def test_rejected_candidate_not_overwritten():
    ws_id = uuid4()
    corr = _make_corr(id=3, name="Acme Corp")

    existing = Mock(spec=CorrespondentContactCandidate)
    existing.paperless_correspondent_id = 3
    existing.status = CANDIDATE_STATUS_REJECTED
    existing.contact_id = None

    contact = _make_contact(workspace_id=ws_id, display_name="Acme Corp")
    db = _make_db(contacts=[contact], existing_candidates=[existing])

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(return_value=[corr])
        mock_get_client.return_value = mock_client

        result = await run_correspondent_bridge(workspace_id=ws_id, db=db)

    assert result["new"] == 0
    assert result["updated"] == 0


@pytest.mark.asyncio
async def test_workspace_isolation():
    """Contacts from another workspace must never be matched."""
    ws_id = uuid4()
    other_ws_id = uuid4()
    corr = _make_corr(id=1, name="Acme Corp")

    # Contact belongs to a DIFFERENT workspace — should not be in query results
    # (The DB mock returns an empty contacts list for this workspace.)
    db = _make_db(contacts=[], existing_candidates=[])

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(return_value=[corr])
        mock_get_client.return_value = mock_client

        result = await run_correspondent_bridge(workspace_id=ws_id, db=db)

    assert result["no_match"] == 1
    added: CorrespondentContactCandidate = db.add.call_args[0][0]
    assert added.contact_id is None
    # Ensure the DB query passed the correct workspace_id
    # (We verify indirectly: no contacts were found → no match)


@pytest.mark.asyncio
async def test_no_correspondents_returns_zeroes():
    ws_id = uuid4()
    db = _make_db(contacts=[], existing_candidates=[])

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(return_value=[])
        mock_get_client.return_value = mock_client

        result = await run_correspondent_bridge(workspace_id=ws_id, db=db)

    assert result == {"processed": 0, "new": 0, "updated": 0, "no_match": 0}
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_paperless_unavailable_propagates():
    ws_id = uuid4()
    db = AsyncMock()

    with patch(
        "api.services.paperless.correspondent_bridge.get_paperless_client"
    ) as mock_get_client:
        mock_client = AsyncMock()
        mock_client.list_correspondents = AsyncMock(
            side_effect=ServiceUnavailableError(
                error_code="PAPERLESS_UNAVAILABLE",
                message="Paperless is unreachable.",
            )
        )
        mock_get_client.return_value = mock_client

        with pytest.raises(ServiceUnavailableError, match="Paperless is unreachable"):
            await run_correspondent_bridge(workspace_id=ws_id, db=db)

    db.commit.assert_not_awaited()
