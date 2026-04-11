"""Tests for S09-001: LLM Grounded QA (Steps 3–5).

Covers:
  - output_parser: JSON parsing, HTML escaping, source hallucination detection
  - context_assembler: card formatting, context trimming
  - llm_client: Ollama /api/chat wrapper, timeout/error handling
  - confidence_scorer: relevance-based downgrade, needs_more_context, no-sources
  - query endpoint: small model path, large model escalation, prefer_fast,
    LLM parse failure fallback, flag-disabled fallback, is_partial, source_refs
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from api.schemas.envelope import EventCard, FileCard, ReminderCard

from contextlib import asynccontextmanager


@asynccontextmanager
async def _noop_slot(priority):
    """No-op replacement for acquire_slot in unit tests."""
    yield


# ---------------------------------------------------------------------------
# output_parser unit tests
# ---------------------------------------------------------------------------


class TestOutputParser:
    """Pure unit tests — no network, no DB."""

    def _import(self):
        from api.services.query.output_parser import parse_output
        return parse_output

    def test_parse_valid_json(self):
        parse_output = self._import()
        raw = json.dumps({
            "answer": "Meeting at 3pm",
            "sources_used": ["Team standup"],
            "confidence": "high",
            "needs_more_context": False,
        })
        result = parse_output(raw, valid_sources=["Team standup"])
        assert result is not None
        assert result.answer == "Meeting at 3pm"
        assert result.sources_used == ["Team standup"]
        assert result.confidence == "high"
        assert result.needs_more_context is False

    def test_parse_strips_markdown_fences(self):
        parse_output = self._import()
        raw = "```json\n" + json.dumps({
            "answer": "Some answer",
            "sources_used": [],
            "confidence": "medium",
            "needs_more_context": False,
        }) + "\n```"
        result = parse_output(raw, valid_sources=[])
        assert result is not None
        assert result.answer == "Some answer"

    def test_parse_invalid_json_returns_none(self):
        parse_output = self._import()
        result = parse_output("not json at all {{ broken", valid_sources=[])
        assert result is None

    def test_parse_missing_required_key_returns_none(self):
        parse_output = self._import()
        # "answer" key is absent
        raw = json.dumps({
            "sources_used": [],
            "confidence": "high",
            "needs_more_context": False,
        })
        result = parse_output(raw, valid_sources=[])
        assert result is None

    def test_parse_html_escapes_answer(self):
        parse_output = self._import()
        raw = json.dumps({
            "answer": "<script>alert('xss')</script>",
            "sources_used": [],
            "confidence": "low",
            "needs_more_context": False,
        })
        result = parse_output(raw, valid_sources=[])
        assert result is not None
        assert "<script>" not in result.answer
        assert "&lt;script&gt;" in result.answer

    def test_parse_hallucinated_source_downgrades_confidence(self):
        parse_output = self._import()
        raw = json.dumps({
            "answer": "Answer here",
            "sources_used": ["real_file.pdf", "invented_source.pdf"],
            "confidence": "high",
            "needs_more_context": False,
        })
        # Only "real_file.pdf" is valid
        result = parse_output(raw, valid_sources=["real_file.pdf"])
        assert result is not None
        # "invented_source.pdf" filtered out
        assert "invented_source.pdf" not in result.sources_used
        assert "real_file.pdf" in result.sources_used
        # confidence downgraded because a hallucinated source appeared
        assert result.confidence == "low"

    def test_parse_all_sources_hallucinated_confidence_low(self):
        parse_output = self._import()
        raw = json.dumps({
            "answer": "Answer",
            "sources_used": ["made_up_source.pdf"],
            "confidence": "high",
            "needs_more_context": False,
        })
        result = parse_output(raw, valid_sources=["real_file.pdf"])
        assert result is not None
        assert result.sources_used == []
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# context_assembler unit tests
# ---------------------------------------------------------------------------


class TestContextAssembler:
    """Pure unit tests — no network, no DB."""

    def _import(self):
        from api.services.query.context_assembler import assemble_context, MAX_CONTEXT_CHARS
        return assemble_context, MAX_CONTEXT_CHARS

    def _make_event_card(self, title: str = "Team standup") -> EventCard:
        return EventCard(
            id=uuid4(),
            priority_score=0.9,
            payload={
                "title": title,
                "start_at": "2026-04-10T10:00:00+00:00",
                "end_at": "2026-04-10T10:30:00+00:00",
                "is_all_day": False,
                "location": "Zoom",
                "calendar_name": "Work",
                "participants": [],
            },
        )

    def _make_file_card(
        self,
        filename: str = "invoice.pdf",
        snippet: str = "Total amount due: $500",
    ) -> FileCard:
        return FileCard(
            id=uuid4(),
            priority_score=0.8,
            payload={
                "filename": filename,
                "snippet": snippet,
                "mime_type": "application/pdf",
                "path": f"/docs/{filename}",
            },
        )

    def test_assemble_formats_event_card(self):
        assemble_context, _ = self._import()
        card = self._make_event_card("Team standup")
        context_text, titles = assemble_context([card])
        assert "Team standup" in context_text
        assert "[Event:" in context_text
        assert "Team standup" in titles

    def test_assemble_formats_file_card(self):
        assemble_context, _ = self._import()
        card = self._make_file_card("invoice.pdf", "Total due: $500")
        context_text, titles = assemble_context([card])
        assert "invoice.pdf" in context_text
        assert "[Document:" in context_text
        assert "Total due: $500" in context_text
        assert "invoice.pdf" in titles

    def test_assemble_trims_at_char_limit(self):
        assemble_context, MAX_CONTEXT_CHARS = self._import()
        # Create a card with a payload that alone exceeds the limit
        big_snippet = "x" * (MAX_CONTEXT_CHARS + 1000)
        cards = [
            self._make_file_card("a.pdf", big_snippet),
            self._make_file_card("b.pdf", "short"),
        ]
        context_text, titles = assemble_context(cards)
        # b.pdf should not appear because we hit the limit after the first card
        assert len(context_text) <= MAX_CONTEXT_CHARS + 500  # some slack for header line
        assert "b.pdf" not in titles

    def test_assemble_returns_source_titles(self):
        assemble_context, _ = self._import()
        cards = [
            self._make_event_card("Meeting A"),
            self._make_file_card("report.pdf"),
        ]
        _, titles = assemble_context(cards)
        assert len(titles) == 2
        assert "Meeting A" in titles
        assert "report.pdf" in titles


# ---------------------------------------------------------------------------
# llm_client unit tests
# ---------------------------------------------------------------------------


class TestLLMClient:
    """Unit tests for the Ollama /api/chat wrapper. httpx and acquire_slot are mocked."""

    def _import(self):
        from api.services.query.llm_client import call_llm
        from api.errors import ServiceUnavailableError
        return call_llm, ServiceUnavailableError

    def _mock_slot(self):
        """Return a patch that makes acquire_slot a no-op async context manager."""
        return patch("api.services.query.llm_client.acquire_slot", _noop_slot)

    @pytest.mark.asyncio
    async def test_call_llm_returns_content(self):
        call_llm, _ = self._import()
        response_json = {
            "model": "phi3:mini",
            "message": {"role": "assistant", "content": '{"answer": "Yes"}'},
            "done": True,
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_json
        mock_response.raise_for_status = MagicMock()

        with (
            self._mock_slot(),
            patch("api.services.query.llm_client.httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await call_llm(
                messages=[{"role": "user", "content": "hello"}],
                model="phi3:mini",
                timeout_s=5.0,
            )

        assert result == '{"answer": "Yes"}'

    @pytest.mark.asyncio
    async def test_call_llm_timeout_raises_service_unavailable(self):
        call_llm, ServiceUnavailableError = self._import()

        with (
            self._mock_slot(),
            patch("api.services.query.llm_client.httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ServiceUnavailableError) as exc_info:
                await call_llm(
                    messages=[{"role": "user", "content": "hello"}],
                    model="phi3:mini",
                    timeout_s=5.0,
                )

        assert exc_info.value.error_code == "LLM_TIMEOUT"

    @pytest.mark.asyncio
    async def test_call_llm_bad_status_raises_service_unavailable(self):
        call_llm, ServiceUnavailableError = self._import()

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )

        with (
            self._mock_slot(),
            patch("api.services.query.llm_client.httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ServiceUnavailableError) as exc_info:
                await call_llm(
                    messages=[{"role": "user", "content": "hello"}],
                    model="phi3:mini",
                    timeout_s=5.0,
                )

        assert exc_info.value.error_code == "LLM_ERROR"


# ---------------------------------------------------------------------------
# confidence_scorer unit tests
# ---------------------------------------------------------------------------


class TestConfidenceScorer:
    """Unit tests for post-hoc confidence override rules."""

    def _import(self):
        from api.services.query.confidence_scorer import score_confidence
        from api.services.query.output_parser import LLMOutput
        return score_confidence, LLMOutput

    def _make_cards(self, top_score: float = 0.9):
        return [
            EventCard(
                id=uuid4(),
                priority_score=top_score,
                payload={"title": "Meeting"},
            )
        ]

    def test_high_confidence_preserved_when_valid(self):
        score_confidence, LLMOutput = self._import()
        out = LLMOutput(answer="Answer", sources_used=["Meeting"], confidence="high")
        assert score_confidence(out, self._make_cards(0.9)) == "high"

    def test_needs_more_context_forces_low(self):
        score_confidence, LLMOutput = self._import()
        out = LLMOutput(answer="Partial", confidence="high", needs_more_context=True)
        assert score_confidence(out, self._make_cards(0.9)) == "low"

    def test_low_relevance_downgrades_high_to_medium(self):
        score_confidence, LLMOutput = self._import()
        out = LLMOutput(answer="Answer", sources_used=["Meeting"], confidence="high")
        assert score_confidence(out, self._make_cards(0.5)) == "medium"

    def test_no_sources_downgrades_high_to_medium(self):
        score_confidence, LLMOutput = self._import()
        out = LLMOutput(answer="Answer", sources_used=[], confidence="high")
        assert score_confidence(out, self._make_cards(0.9)) == "medium"

    def test_medium_not_downgraded_by_relevance(self):
        score_confidence, LLMOutput = self._import()
        out = LLMOutput(answer="Answer", sources_used=["Meeting"], confidence="medium")
        # relevance < 0.6 only affects "high" → "medium", not "medium" → "low"
        assert score_confidence(out, self._make_cards(0.3)) == "medium"

    def test_low_confidence_unchanged(self):
        score_confidence, LLMOutput = self._import()
        out = LLMOutput(answer="Answer", sources_used=["Meeting"], confidence="low")
        assert score_confidence(out, self._make_cards(0.9)) == "low"


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------

_SAMPLE_CARDS = [
    EventCard(
        id=uuid4(),
        priority_score=0.9,
        payload={
            "title": "Team standup",
            "start_at": "2026-04-10T10:00:00+00:00",
            "end_at": "2026-04-10T10:30:00+00:00",
            "is_all_day": False,
            "location": None,
            "calendar_name": "Work",
            "participants": [],
        },
    )
]

_SMALL_MODEL_RESPONSE = json.dumps({
    "answer": "You have a Team standup at 10am.",
    "sources_used": ["Team standup"],
    "confidence": "high",
    "needs_more_context": False,
})

_SMALL_NEEDS_MORE_RESPONSE = json.dumps({
    "answer": "Partial answer",
    "sources_used": [],
    "confidence": "medium",
    "needs_more_context": True,
})

_LARGE_MODEL_RESPONSE = json.dumps({
    "answer": "Full detailed answer from large model.",
    "sources_used": ["Team standup"],
    "confidence": "high",
    "needs_more_context": False,
})


@pytest.mark.asyncio
async def test_query_uses_small_model_when_llm_enabled(client, auth_tokens):
    """When search_all returns cards and llm_query_enabled flag is set,
    the endpoint calls phi3:mini and returns the grounded answer."""
    ws_id = auth_tokens["workspace_id"]

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", new_callable=AsyncMock) as mock_llm,
    ):
        mock_search.return_value = (_SAMPLE_CARDS, {"event": 1})
        mock_llm.return_value = _SMALL_MODEL_RESPONSE

        response = await client.post(
            "/api/v1/query",
            # Use a query that won't match any deterministic pattern
            json={"query": "tell me about the quarterly review project", "workspace_id": str(ws_id)},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer_text"] == "You have a Team standup at 10am."
    assert data["metadata"]["query_path"] == "small_model"
    assert data["confidence_level"] == "high"
    # Cards should still be returned alongside the answer
    assert len(data["cards"]) > 0


@pytest.mark.asyncio
async def test_query_escalates_to_large_model_on_needs_more_context(client, auth_tokens):
    """When small model returns needs_more_context=true and prefer_fast=false,
    the large model is called and its response is returned."""
    ws_id = auth_tokens["workspace_id"]
    call_count = []

    async def _mock_llm(messages, model, timeout_s, temperature=0.1):
        call_count.append(model)
        if model == "phi3:mini":
            return _SMALL_NEEDS_MORE_RESPONSE
        return _LARGE_MODEL_RESPONSE

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", side_effect=_mock_llm),
    ):
        mock_search.return_value = (_SAMPLE_CARDS, {"event": 1})

        response = await client.post(
            "/api/v1/query",
            json={
                "query": "summarize the budget discussion from last sprint",
                "workspace_id": str(ws_id),
                "prefer_fast": False,
            },
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "llama3.1:8b" in call_count
    assert data["metadata"]["query_path"] == "large_model"
    assert data["answer_text"] == "Full detailed answer from large model."


@pytest.mark.asyncio
async def test_query_skips_large_model_when_prefer_fast(client, auth_tokens):
    """When prefer_fast=true, the large model is NOT called even if
    small model returns needs_more_context=true."""
    ws_id = auth_tokens["workspace_id"]
    call_count = []

    async def _mock_llm(messages, model, timeout_s, temperature=0.1):
        call_count.append(model)
        return _SMALL_NEEDS_MORE_RESPONSE

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", side_effect=_mock_llm),
    ):
        mock_search.return_value = (_SAMPLE_CARDS, {"event": 1})

        response = await client.post(
            "/api/v1/query",
            json={
                "query": "tell me about the quarterly review project",
                "workspace_id": str(ws_id),
                "prefer_fast": True,
            },
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200
    # Large model must not have been called
    assert "llama3.1:8b" not in call_count
    assert "phi3:mini" in call_count


@pytest.mark.asyncio
async def test_query_falls_back_to_search_on_llm_parse_failure(client, auth_tokens):
    """When the LLM returns unparseable JSON, the endpoint falls back to
    returning plain search cards (no answer_text) with is_partial=true."""
    ws_id = auth_tokens["workspace_id"]

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", new_callable=AsyncMock) as mock_llm,
    ):
        mock_search.return_value = (_SAMPLE_CARDS, {"event": 1})
        mock_llm.return_value = "not valid json at all"

        response = await client.post(
            "/api/v1/query",
            json={"query": "tell me about the quarterly review project", "workspace_id": str(ws_id)},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer_text"] is None
    assert data["metadata"]["is_partial"] is True
    assert data["metadata"]["query_path"] == "semantic"
    assert len(data["cards"]) > 0


@pytest.mark.asyncio
async def test_query_populates_sources_from_llm_output(client, auth_tokens):
    """When the LLM cites sources that match card titles, the response
    envelope populates the sources array with SourceRef objects."""
    ws_id = auth_tokens["workspace_id"]

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", new_callable=AsyncMock) as mock_llm,
    ):
        mock_search.return_value = (_SAMPLE_CARDS, {"event": 1})
        mock_llm.return_value = _SMALL_MODEL_RESPONSE

        response = await client.post(
            "/api/v1/query",
            json={"query": "tell me about the quarterly review project", "workspace_id": str(ws_id)},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["sources"]) > 0
    assert data["sources"][0]["title"] == "Team standup"
    assert data["sources"][0]["type"] == "event"


@pytest.mark.asyncio
async def test_query_llm_timeout_returns_partial(client, auth_tokens):
    """When Ollama times out, response is cards-only with is_partial=true."""
    from api.errors import ServiceUnavailableError

    ws_id = auth_tokens["workspace_id"]

    with (
        patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
        patch("api.routers.query.call_llm", new_callable=AsyncMock) as mock_llm,
    ):
        mock_search.return_value = (_SAMPLE_CARDS, {"event": 1})
        mock_llm.side_effect = ServiceUnavailableError(
            error_code="LLM_TIMEOUT", message="timed out"
        )

        response = await client.post(
            "/api/v1/query",
            json={"query": "tell me about the quarterly review project", "workspace_id": str(ws_id)},
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer_text"] is None
    assert data["metadata"]["is_partial"] is True
    assert len(data["cards"]) > 0


@pytest.mark.asyncio
async def test_query_falls_back_when_llm_flag_disabled(client, auth_tokens):
    """When llm_query_enabled is not in _ENABLED_FLAGS, the LLM is never
    called and the plain search-card response is returned."""
    from api.middleware.feature_gate import _ENABLED_FLAGS

    ws_id = auth_tokens["workspace_id"]

    _ENABLED_FLAGS.discard("llm_query_enabled")
    try:
        with (
            patch("api.routers.query.search_all", new_callable=AsyncMock) as mock_search,
            patch("api.routers.query.call_llm", new_callable=AsyncMock) as mock_llm,
        ):
            mock_search.return_value = (_SAMPLE_CARDS, {"event": 1})

            response = await client.post(
                "/api/v1/query",
                json={"query": "tell me about the quarterly review project", "workspace_id": str(ws_id)},
                headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["answer_text"] is None
        mock_llm.assert_not_called()
    finally:
        _ENABLED_FLAGS.add("llm_query_enabled")
