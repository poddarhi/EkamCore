"""Unit tests for ResponseEnvelope schema (S04-006).

Validates:
- All card subtypes construct and serialise correctly.
- Discriminated union (`Card`) rejects unknown types.
- `make_envelope` helper produces a well-formed envelope.
- ResponseMetadata and CacheHint defaults.
- Round-trip: model_dump → ResponseEnvelope.model_validate.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.schemas.envelope import (
    CacheHint,
    EventCard,
    FileCard,
    PackCard,
    PersonCard,
    PhotoCard,
    ReminderCard,
    ResponseEnvelope,
    ResponseMetadata,
    SourceRef,
    StatusCard,
    SuggestedAction,
    SuggestionCard,
    make_envelope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eid() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# Card subtype construction
# ---------------------------------------------------------------------------

class TestCardSubtypes:
    def test_event_card_type_literal(self):
        c = EventCard(id=uuid4())
        assert c.type == "event"
        assert c.priority_score == 0.0
        assert c.source_ids == []
        assert c.payload == {}

    def test_reminder_card_type_literal(self):
        c = ReminderCard(id=uuid4(), priority_score=0.9)
        assert c.type == "reminder"
        assert c.priority_score == 0.9

    def test_status_card_type_literal(self):
        c = StatusCard(id=uuid4(), payload={"time_of_day": "morning"})
        assert c.type == "status"
        assert c.payload["time_of_day"] == "morning"

    def test_person_card_type_literal(self):
        c = PersonCard(id=uuid4())
        assert c.type == "person"

    def test_file_card_type_literal(self):
        c = FileCard(id=uuid4())
        assert c.type == "file"

    def test_photo_card_type_literal(self):
        c = PhotoCard(id=uuid4())
        assert c.type == "photo"

    def test_suggestion_card_type_literal(self):
        c = SuggestionCard(id=uuid4())
        assert c.type == "suggestion"

    def test_pack_card_type_literal(self):
        c = PackCard(id=uuid4())
        assert c.type == "pack"


# ---------------------------------------------------------------------------
# Discriminated union routing
# ---------------------------------------------------------------------------

class TestDiscriminatedUnion:
    """ResponseEnvelope.cards uses Card = Annotated[..., Field(discriminator='type')]."""

    def test_event_card_round_trip_through_envelope(self):
        card = EventCard(id=uuid4(), priority_score=0.8, payload={"title": "Standup"})
        env = ResponseEnvelope(cards=[card], metadata=ResponseMetadata())
        dumped = env.model_dump()
        restored = ResponseEnvelope.model_validate(dumped)
        assert restored.cards[0].type == "event"
        assert restored.cards[0].payload["title"] == "Standup"

    def test_mixed_card_types_round_trip(self):
        cards = [
            EventCard(id=uuid4(), priority_score=0.9),
            ReminderCard(id=uuid4(), priority_score=0.7),
            StatusCard(id=uuid4(), priority_score=0.5),
        ]
        env = ResponseEnvelope(cards=cards, metadata=ResponseMetadata())
        dumped = env.model_dump()
        restored = ResponseEnvelope.model_validate(dumped)
        types = [c.type for c in restored.cards]
        assert types == ["event", "reminder", "status"]

    def test_unknown_card_type_raises_validation_error(self):
        raw = {
            "answer_text": None,
            "confidence_level": "deterministic",
            "sources": [],
            "cards": [{"type": "unknown_type", "id": str(uuid4())}],
            "suggested_actions": [],
            "metadata": {"query_path": "deterministic", "latency_ms": 0, "is_partial": False},
        }
        with pytest.raises(ValidationError):
            ResponseEnvelope.model_validate(raw)


# ---------------------------------------------------------------------------
# ResponseMetadata
# ---------------------------------------------------------------------------

class TestResponseMetadata:
    def test_defaults(self):
        m = ResponseMetadata()
        assert m.query_path == "deterministic"
        assert m.latency_ms == 0
        assert m.is_partial is False
        assert m.cache_hint is None

    def test_with_cache_hint(self):
        m = ResponseMetadata(cache_hint=CacheHint(ttl_seconds=300))
        assert m.cache_hint is not None
        assert m.cache_hint.ttl_seconds == 300

    def test_query_path_literals(self):
        for path in ("deterministic", "semantic", "small_model", "large_model"):
            m = ResponseMetadata(query_path=path)
            assert m.query_path == path

    def test_invalid_query_path_raises(self):
        with pytest.raises(ValidationError):
            ResponseMetadata(query_path="magic")


# ---------------------------------------------------------------------------
# ResponseEnvelope defaults
# ---------------------------------------------------------------------------

class TestResponseEnvelopeDefaults:
    def test_empty_envelope(self):
        env = ResponseEnvelope(metadata=ResponseMetadata())
        assert env.answer_text is None
        assert env.confidence_level == "deterministic"
        assert env.sources == []
        assert env.cards == []
        assert env.suggested_actions == []

    def test_confidence_level_literals(self):
        for level in ("deterministic", "high", "medium", "low"):
            env = ResponseEnvelope(confidence_level=level, metadata=ResponseMetadata())
            assert env.confidence_level == level

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValidationError):
            ResponseEnvelope(confidence_level="very_sure", metadata=ResponseMetadata())


# ---------------------------------------------------------------------------
# make_envelope helper
# ---------------------------------------------------------------------------

class TestMakeEnvelope:
    def test_no_args_returns_valid_envelope(self):
        env = make_envelope()
        assert isinstance(env, ResponseEnvelope)
        assert env.cards == []
        assert env.sources == []
        assert env.suggested_actions == []
        assert env.answer_text is None
        assert env.confidence_level == "deterministic"
        assert env.metadata.query_path == "deterministic"
        assert env.metadata.latency_ms == 0
        assert env.metadata.is_partial is False
        assert env.metadata.cache_hint is None

    def test_cards_passed_through(self):
        cards = [EventCard(id=uuid4()), ReminderCard(id=uuid4())]
        env = make_envelope(cards=cards)
        assert len(env.cards) == 2
        assert env.cards[0].type == "event"
        assert env.cards[1].type == "reminder"

    def test_latency_ms_set(self):
        env = make_envelope(latency_ms=42)
        assert env.metadata.latency_ms == 42

    def test_query_path_set(self):
        env = make_envelope(query_path="semantic")
        assert env.metadata.query_path == "semantic"

    def test_confidence_level_set(self):
        env = make_envelope(confidence_level="high")
        assert env.confidence_level == "high"

    def test_answer_text_set(self):
        env = make_envelope(answer_text="Here are your events.")
        assert env.answer_text == "Here are your events."

    def test_sources_passed_through(self):
        sources = [SourceRef(type="event", id=uuid4(), title="Standup", relevance=0.9)]
        env = make_envelope(sources=sources)
        assert len(env.sources) == 1
        assert env.sources[0].title == "Standup"

    def test_suggested_actions_passed_through(self):
        actions = [SuggestedAction(action_type="open_calendar", label="Open Calendar")]
        env = make_envelope(suggested_actions=actions)
        assert len(env.suggested_actions) == 1
        assert env.suggested_actions[0].action_type == "open_calendar"

    def test_is_partial_set(self):
        env = make_envelope(is_partial=True)
        assert env.metadata.is_partial is True

    def test_cache_hint_set(self):
        env = make_envelope(cache_hint=CacheHint(ttl_seconds=60))
        assert env.metadata.cache_hint is not None
        assert env.metadata.cache_hint.ttl_seconds == 60

    def test_none_cards_coerces_to_empty_list(self):
        env = make_envelope(cards=None)
        assert env.cards == []

    def test_none_sources_coerces_to_empty_list(self):
        env = make_envelope(sources=None)
        assert env.sources == []

    def test_none_suggested_actions_coerces_to_empty_list(self):
        env = make_envelope(suggested_actions=None)
        assert env.suggested_actions == []


# ---------------------------------------------------------------------------
# Serialisation shape (model_dump matches expected JSON keys)
# ---------------------------------------------------------------------------

class TestSerializationShape:
    def test_envelope_top_level_keys(self):
        env = make_envelope()
        d = env.model_dump()
        assert set(d.keys()) == {
            "answer_text",
            "confidence_level",
            "sources",
            "cards",
            "suggested_actions",
            "metadata",
        }

    def test_metadata_keys(self):
        env = make_envelope()
        d = env.model_dump()["metadata"]
        assert set(d.keys()) == {"query_path", "latency_ms", "is_partial", "cache_hint"}

    def test_card_keys(self):
        env = make_envelope(cards=[EventCard(id=uuid4(), priority_score=0.7)])
        card_d = env.model_dump()["cards"][0]
        assert set(card_d.keys()) == {"type", "id", "priority_score", "source_ids", "payload"}

    def test_source_ref_keys(self):
        src = SourceRef(type="event", id=uuid4(), title="Meeting")
        env = make_envelope(sources=[src])
        src_d = env.model_dump()["sources"][0]
        assert set(src_d.keys()) == {"type", "id", "title", "relevance"}
