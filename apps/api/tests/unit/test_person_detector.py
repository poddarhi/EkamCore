"""Unit tests for person name detector (S14-011).

Exercises span extraction and the ILIKE-matching logic via a mock
DB session that returns pre-seeded TrustedPerson rows.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from api.services.query.person_detector import (
    _extract_spans,
    detect_person_references,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _mock_db(persons):
    """Return an AsyncSession mock whose execute returns ``persons``
    as scalars."""
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=persons)
    result_mock = MagicMock()
    result_mock.scalars = MagicMock(return_value=scalars_mock)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


def _person(name, pid=None):
    return SimpleNamespace(
        id=pid or uuid4(),
        display_name=name,
        workspace_id=uuid4(),
        deleted_at=None,
    )


class TestExtractSpans:
    def test_simple_name(self):
        spans = _extract_spans("Who is Alice Smith?")
        assert "Alice" in spans
        assert "Alice Smith" in spans

    def test_stop_words_removed(self):
        spans = _extract_spans("what is the plan?")
        # "what", "is", "the" are stop words; only "plan" survives
        assert "plan" in spans
        assert "what" not in spans

    def test_single_char_tokens_skipped(self):
        spans = _extract_spans("I see a big thing")
        # "I" and "a" are single-char or stop words
        assert all(len(s) > 1 for s in spans)


class TestDetectPersonReferences:
    async def test_alice_matches_alice_smith(self):
        alice = _person("Alice Smith")
        db = _mock_db([alice])
        result = await detect_person_references(
            "What files does Alice have?", uuid4(), db
        )
        assert len(result) == 1
        assert result[0].display_name == "Alice Smith"

    async def test_full_name_matches(self):
        bob = _person("Bob Jones")
        db = _mock_db([bob])
        result = await detect_person_references(
            "Show me Bob Jones photos", uuid4(), db
        )
        assert len(result) == 1

    async def test_no_person_reference(self):
        db = _mock_db([])
        result = await detect_person_references(
            "How's the weather?", uuid4(), db
        )
        assert result == []

    async def test_max_5_returned(self):
        persons = [_person(f"Person{i}") for i in range(10)]
        db = _mock_db(persons)
        result = await detect_person_references(
            "Person0 Person1 Person2 Person3 Person4 Person5",
            uuid4(),
            db,
        )
        assert len(result) <= 5

    async def test_deduplication(self):
        alice = _person("Alice Smith")
        db = _mock_db([alice, alice])
        result = await detect_person_references(
            "Alice Smith", uuid4(), db
        )
        assert len(result) == 1


class TestPatternIntegration:
    def test_who_is_pattern(self):
        from api.services.query.patterns import classify_query

        # "who is X" is caught by the existing contact_search pattern
        # (registered earlier). Person-specific context enrichment
        # happens at Step 1.5 via person_detector, not the pattern.
        intent = classify_query("who is Alice Smith?")
        assert intent is not None
        assert intent.intent_type in ("contact_search", "person_who_is")

    def test_photos_of_pattern(self):
        from api.services.query.patterns import classify_query

        intent = classify_query("photos of Bob")
        assert intent is not None
        assert intent.intent_type == "person_photos"
        assert intent.params["person_name"] == "Bob"

    def test_last_seen_pattern(self):
        from api.services.query.patterns import classify_query

        intent = classify_query("when did I last see Carol?")
        assert intent is not None
        assert intent.intent_type == "person_last_seen"
        assert "Carol" in intent.params["person_name"]

    def test_files_pattern(self):
        from api.services.query.patterns import classify_query

        intent = classify_query("what files does Dave have?")
        assert intent is not None
        assert intent.intent_type == "person_files"
        assert "Dave" in intent.params["person_name"]

    def test_non_person_query_unchanged(self):
        from api.services.query.patterns import classify_query

        intent = classify_query("meetings tomorrow")
        assert intent is not None
        assert intent.intent_type != "person_who_is"
