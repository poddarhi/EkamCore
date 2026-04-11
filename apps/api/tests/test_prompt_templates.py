"""Tests for G-04: Prompt template library.

Covers:
  - Template loader: config loading, version resolution
  - Recap summary: message construction, output format
  - Person context: message construction, model selection
  - Embed preprocess: chunk formatting with metadata prefix
"""

from __future__ import annotations

import pytest


# ── Template loader ─────────────────────────────────────────────────────────


class TestTemplateLoader:

    def test_load_grounded_qa(self):
        from api.services.query.prompts import get_template
        mod = get_template("grounded_qa")
        assert hasattr(mod, "build_messages")
        assert hasattr(mod, "SYSTEM_PROMPT")

    def test_load_query_classify(self):
        from api.services.query.prompts import get_template
        mod = get_template("query_classify")
        assert hasattr(mod, "build_classify_messages")

    def test_load_recap_summary(self):
        from api.services.query.prompts import get_template
        mod = get_template("recap_summary")
        assert hasattr(mod, "build_messages")
        assert hasattr(mod, "MODEL")

    def test_load_person_context(self):
        from api.services.query.prompts import get_template
        mod = get_template("person_context")
        assert hasattr(mod, "build_messages")
        assert hasattr(mod, "select_model")

    def test_load_embed_preprocess(self):
        from api.services.query.prompts import get_template
        mod = get_template("embed_preprocess")
        assert hasattr(mod, "format_chunk_for_embedding")

    def test_unknown_template_raises_key_error(self):
        from api.services.query.prompts import get_template
        with pytest.raises(KeyError):
            get_template("nonexistent_template")


# ── Recap summary ──────────────────────────────────────────────────────────


class TestRecapSummary:

    def test_build_messages_daily(self):
        from api.services.query.prompts.recap_summary_v1 import build_messages
        msgs = build_messages(period="daily", event_count=3, reminder_count=2, file_count=1)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "daily" in msgs[1]["content"]
        assert "Events: 3" in msgs[1]["content"]
        assert "Reminders: 2" in msgs[1]["content"]

    def test_build_messages_with_highlights(self):
        from api.services.query.prompts.recap_summary_v1 import build_messages
        msgs = build_messages(
            period="weekly", event_count=10, reminder_count=5, file_count=3,
            highlights=["Team standup", "Budget review"],
        )
        assert "Team standup" in msgs[1]["content"]
        assert "Budget review" in msgs[1]["content"]

    def test_model_and_timeout(self):
        from api.services.query.prompts.recap_summary_v1 import MODEL, TIMEOUT_S, TEMPERATURE
        assert MODEL == "llama3.1:8b"
        assert TIMEOUT_S == 10.0
        assert TEMPERATURE == 0.3


# ── Person context ─────────────────────────────────────────────────────────


class TestPersonContext:

    def test_build_messages_basic(self):
        from api.services.query.prompts.person_context_v1 import build_messages
        msgs = build_messages(
            person_name="Sarah Johnson",
            organization="Acme Corp",
            emails=["sarah@acme.com"],
            phones=["555-1234"],
            linked_events=["Team standup", "Budget review"],
            linked_files=["q1-report.pdf"],
            linked_reminders=["Follow up with Sarah"],
            question="When is my next meeting with Sarah?",
        )
        assert len(msgs) == 2
        assert "<person-context>" in msgs[1]["content"]
        assert "Sarah Johnson" in msgs[1]["content"]
        assert "Acme Corp" in msgs[1]["content"]
        assert "<question>" in msgs[1]["content"]

    def test_select_model_small(self):
        from api.services.query.prompts.person_context_v1 import select_model
        model, timeout = select_model(linked_count=5)
        assert model == "phi3:mini"
        assert timeout == 5.0

    def test_select_model_large(self):
        from api.services.query.prompts.person_context_v1 import select_model
        model, timeout = select_model(linked_count=25)
        assert model == "llama3.1:8b"
        assert timeout == 15.0


# ── Embed preprocess ───────────────────────────────────────────────────────


class TestEmbedPreprocess:

    def test_format_with_all_metadata(self):
        from api.services.query.prompts.embed_preprocess_v1 import format_chunk_for_embedding
        result = format_chunk_for_embedding(
            chunk_text="Total revenue was $10M.",
            filename="q1-report.pdf",
            mime_type="application/pdf",
            date="2026-04-10",
        )
        assert result.startswith("File: q1-report.pdf | Type: application/pdf | Date: 2026-04-10")
        assert "Total revenue was $10M." in result

    def test_format_with_no_metadata(self):
        from api.services.query.prompts.embed_preprocess_v1 import format_chunk_for_embedding
        result = format_chunk_for_embedding(chunk_text="Just text.")
        assert result == "Just text."

    def test_format_with_partial_metadata(self):
        from api.services.query.prompts.embed_preprocess_v1 import format_chunk_for_embedding
        result = format_chunk_for_embedding(chunk_text="Content", filename="doc.txt")
        assert result.startswith("File: doc.txt")
        assert "Type:" not in result
        assert "Content" in result
