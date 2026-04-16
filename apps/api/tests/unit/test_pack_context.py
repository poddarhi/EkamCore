"""Unit tests for PackContext capability enforcement and outputs (S14-003).

These tests avoid the DB — they exercise the capability gate,
LLM quota, card queue, sanitization, and consent stripping logic
directly. The methods that actually query tables are covered by
the integration test under ``tests/integration/``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from api.errors import CapabilityDeniedError, PackLlmQuotaExceededError
from api.services.pack.manifest_loader import (
    PackManifest,
    ResourceLimits,
    ScheduleConfig,
)
from api.services.pack.pack_context import PackContext
from api.services.pack.pack_context_factory import PackContextFactory
from api.services.pack.sanitizer import sanitize_payload, sanitize_text


def _build_manifest(
    *,
    capabilities: list[str] | None = None,
    card_types: list[str] | None = None,
    max_llm_calls: int = 5,
) -> PackManifest:
    return PackManifest(
        pack_id="testpack",
        name="Test",
        version="1.0.0",
        description="test",
        author="test",
        capabilities=capabilities or ["read:contacts", "invoke:llm"],
        resource_limits=ResourceLimits(
            max_execution_time_seconds=60,
            max_memory_mb=64,
            max_llm_calls_per_run=max_llm_calls,
        ),
        card_types=card_types or ["follow_up_suggestion"],
        schedule=ScheduleConfig(),
    )


def _build_context(
    *,
    capabilities: set[str] | None = None,
    consent_active: bool = True,
    max_llm_calls: int = 5,
    card_types: set[str] | None = None,
    llm_callable=None,
) -> PackContext:
    return PackContext(
        workspace_id=uuid4(),
        capabilities=capabilities
        if capabilities is not None
        else {"read:contacts", "invoke:llm"},
        resource_limits=ResourceLimits(
            max_execution_time_seconds=60,
            max_memory_mb=64,
            max_llm_calls_per_run=max_llm_calls,
        ),
        allowed_card_types=card_types
        if card_types is not None
        else {"follow_up_suggestion"},
        consent_active=consent_active,
        pack_id="testpack",
        pack_run_id=None,
        db=None,  # type: ignore[arg-type]
        llm_callable=llm_callable,
    )


# ── Capability gate ───────────────────────────────────────────────────────


class TestCapabilityGate:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_contacts_without_capability_raises(self):
        ctx = _build_context(capabilities=set())
        with pytest.raises(CapabilityDeniedError) as excinfo:
            await ctx.get_contacts()
        assert excinfo.value.error_code == "CAPABILITY_DENIED"
        assert "read:contacts" in excinfo.value.message

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_persons_without_capability_raises(self):
        ctx = _build_context(capabilities=set())
        with pytest.raises(CapabilityDeniedError):
            await ctx.get_persons()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_persons_without_consent_raises(self):
        ctx = _build_context(
            capabilities={"read:trusted_persons"},
            consent_active=False,
        )
        with pytest.raises(CapabilityDeniedError) as excinfo:
            await ctx.get_persons()
        assert "consent is not active" in excinfo.value.message

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_photos_for_person_requires_both_caps(self):
        ctx = _build_context(
            capabilities={"read:photos"},  # missing read:graph_edges
            consent_active=True,
        )
        with pytest.raises(CapabilityDeniedError) as excinfo:
            await ctx.get_photos_for_person(uuid4())
        assert "read:graph_edges" in excinfo.value.message

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_reminder_without_write_cap_raises(self):
        ctx = _build_context(capabilities=set())
        with pytest.raises(CapabilityDeniedError):
            await ctx.create_reminder(
                title="x", created_by=uuid4()
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_traverse_graph_without_cap_raises(self):
        ctx = _build_context(capabilities=set())
        with pytest.raises(CapabilityDeniedError):
            await ctx.traverse_graph(uuid4())


# ── LLM quota ─────────────────────────────────────────────────────────────


class TestLlmQuota:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_within_quota_calls_llm_and_returns_sanitized(self):
        mock = AsyncMock(return_value="<b>hello</b>\n  world")
        ctx = _build_context(
            capabilities={"invoke:llm"},
            max_llm_calls=3,
            llm_callable=mock,
        )
        out = await ctx.ask_llm("hi")
        assert out == "hello\nworld"
        assert ctx.llm_calls_used == 1
        mock.assert_awaited_once()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_quota_exhaustion_raises_and_does_not_call_llm(self):
        mock = AsyncMock(return_value="x")
        ctx = _build_context(
            capabilities={"invoke:llm"},
            max_llm_calls=2,
            llm_callable=mock,
        )
        await ctx.ask_llm("one")
        await ctx.ask_llm("two")
        with pytest.raises(PackLlmQuotaExceededError) as excinfo:
            await ctx.ask_llm("three")
        assert excinfo.value.error_code == "PACK_LLM_QUOTA_EXCEEDED"
        # The third call raised before the callable could run.
        assert mock.await_count == 2

    @pytest.mark.asyncio(loop_scope="session")
    async def test_failed_call_still_consumes_quota(self):
        async def _boom(*_a, **_kw):
            raise RuntimeError("upstream")

        ctx = _build_context(
            capabilities={"invoke:llm"},
            max_llm_calls=2,
            llm_callable=_boom,
        )
        with pytest.raises(RuntimeError):
            await ctx.ask_llm("x")
        # Failure counts so retries don't spin forever.
        assert ctx.llm_calls_used == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_ask_llm_without_cap_raises(self):
        ctx = _build_context(capabilities=set())
        with pytest.raises(CapabilityDeniedError):
            await ctx.ask_llm("hi")


# ── Card production ──────────────────────────────────────────────────────


class TestCardProduction:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_valid_card_type_queues_sanitized_payload(self):
        ctx = _build_context()
        await ctx.produce_card(
            "follow_up_suggestion",
            {
                "name": "Alice <script>alert(1)</script>",
                "reason": "haven't\x00talked  in   weeks",
                "days": 14,
            },
        )
        assert len(ctx.cards) == 1
        card = ctx.cards[0]
        assert card["card_type"] == "follow_up_suggestion"
        assert "<script>" not in card["payload"]["name"]
        # Tags are stripped; inner text survives — the sanitizer
        # protects against HTML rendering, not content filtering.
        assert card["payload"]["name"] == "Alice alert(1)"
        assert "\x00" not in card["payload"]["reason"]
        # NUL bytes dropped (not replaced); internal whitespace
        # runs collapsed to a single space.
        assert card["payload"]["reason"] == "haven'ttalked in weeks"
        assert card["payload"]["days"] == 14

    @pytest.mark.asyncio(loop_scope="session")
    async def test_undeclared_card_type_raises(self):
        ctx = _build_context(card_types={"follow_up_suggestion"})
        with pytest.raises(CapabilityDeniedError) as excinfo:
            await ctx.produce_card("weekly_summary", {"x": 1})
        assert "weekly_summary" in excinfo.value.message

    @pytest.mark.asyncio(loop_scope="session")
    async def test_non_dict_payload_raises(self):
        ctx = _build_context()
        with pytest.raises(CapabilityDeniedError):
            await ctx.produce_card(
                "follow_up_suggestion", ["not", "a", "dict"]  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_cards_property_returns_copy(self):
        ctx = _build_context()
        await ctx.produce_card("follow_up_suggestion", {"x": 1})
        snapshot = ctx.cards
        snapshot.append({"forged": True})
        # Mutating the snapshot must not bleed back into the context.
        assert len(ctx.cards) == 1


# ── Sanitizer standalone ─────────────────────────────────────────────────


class TestSanitizer:
    def test_strips_tags(self):
        assert sanitize_text("<b>hi</b>") == "hi"

    def test_drops_control_chars_but_keeps_newlines(self):
        # NUL dropped (not replaced); newline preserved.
        assert sanitize_text("a\x00b\nc") == "ab\nc"

    def test_collapses_horizontal_whitespace(self):
        assert sanitize_text("a   b\t\tc") == "a b c"

    def test_truncates_at_max_len(self):
        assert len(sanitize_text("x" * 5000, max_len=100)) == 100

    def test_rejects_non_str(self):
        with pytest.raises(TypeError):
            sanitize_text(123)  # type: ignore[arg-type]

    def test_sanitize_payload_walks_nested(self):
        out = sanitize_payload(
            {"a": "<i>x</i>", "b": [1, "<s>y</s>", {"c": "<br>"}]}
        )
        assert out == {"a": "x", "b": [1, "y", {"c": ""}]}

    def test_sanitize_payload_preserves_non_strings(self):
        out = sanitize_payload({"n": 1, "f": 1.5, "b": True, "none": None})
        assert out == {"n": 1, "f": 1.5, "b": True, "none": None}


# ── Factory consent stripping ────────────────────────────────────────────


class TestPackContextFactory:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_strips_consent_caps_when_consent_off(self):
        manifest = _build_manifest(
            capabilities=[
                "read:contacts",
                "read:trusted_persons",
                "read:graph_edges",
                "query:graph",
                "invoke:llm",
            ]
        )
        factory = PackContextFactory(
            llm_callable=AsyncMock(return_value=""),
            consent_checker=AsyncMock(return_value=False),
        )
        ctx = await factory.create(
            workspace_id=uuid4(),
            manifest=manifest,
            db=None,  # type: ignore[arg-type]
        )
        assert "read:contacts" in ctx.capabilities
        assert "invoke:llm" in ctx.capabilities
        assert "read:trusted_persons" not in ctx.capabilities
        assert "read:graph_edges" not in ctx.capabilities
        assert "query:graph" not in ctx.capabilities
        assert ctx.consent_active is False

    @pytest.mark.asyncio(loop_scope="session")
    async def test_keeps_all_caps_when_consent_on(self):
        manifest = _build_manifest(
            capabilities=[
                "read:contacts",
                "read:trusted_persons",
                "query:graph",
            ]
        )
        factory = PackContextFactory(
            llm_callable=AsyncMock(return_value=""),
            consent_checker=AsyncMock(return_value=True),
        )
        ctx = await factory.create(
            workspace_id=uuid4(),
            manifest=manifest,
            db=None,  # type: ignore[arg-type]
        )
        assert ctx.capabilities == {
            "read:contacts",
            "read:trusted_persons",
            "query:graph",
        }
        assert ctx.consent_active is True

    @pytest.mark.asyncio(loop_scope="session")
    async def test_factory_passes_manifest_card_types_through(self):
        manifest = _build_manifest(
            card_types=["follow_up_suggestion", "weekly_summary"]
        )
        factory = PackContextFactory(
            llm_callable=AsyncMock(return_value=""),
            consent_checker=AsyncMock(return_value=True),
        )
        ctx = await factory.create(
            workspace_id=uuid4(),
            manifest=manifest,
            db=None,  # type: ignore[arg-type]
        )
        # produce_card with a declared type succeeds.
        await ctx.produce_card("follow_up_suggestion", {})
        await ctx.produce_card("weekly_summary", {})
        # Anything else is denied.
        with pytest.raises(CapabilityDeniedError):
            await ctx.produce_card("relationship_reminder", {})
