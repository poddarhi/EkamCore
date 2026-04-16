"""Unit tests for PackRunner sandbox execution (S14-004).

Uses an in-memory mock DB session (AsyncMock) and stub workflows.
The runner's DB writes go through ``db.add`` + ``db.flush`` which
we assert on by inspecting the mock's call log. For full
integration (real pack_runs / pack_cards rows) see
``tests/integration/test_pack_sandbox.py``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from api.services.pack.manifest_loader import (
    ManifestLoader,
    PackManifest,
    ResourceLimits,
    ScheduleConfig,
)
from api.services.pack.pack_context import PackContext
from api.services.pack.pack_context_factory import PackContextFactory
from api.services.pack.pack_runner import (
    MAX_CARD_PAYLOAD_BYTES,
    PackRunner,
    PackRunResult,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _manifest(
    *, max_execution_time: int = 5, max_llm_calls: int = 3
) -> PackManifest:
    return PackManifest(
        pack_id="testpack",
        name="Test Pack",
        version="1.0.0",
        description="test",
        author="test",
        capabilities=["read:contacts", "invoke:llm"],
        resource_limits=ResourceLimits(
            max_execution_time_seconds=max_execution_time,
            max_memory_mb=64,
            max_llm_calls_per_run=max_llm_calls,
        ),
        card_types=["follow_up_suggestion"],
        schedule=ScheduleConfig(),
    )


def _loader(manifest: PackManifest) -> ManifestLoader:
    loader = ManifestLoader(packs_dir="/dev/null")
    loader._manifests[manifest.pack_id] = manifest
    return loader


def _factory() -> PackContextFactory:
    return PackContextFactory(
        llm_callable=AsyncMock(return_value="llm-response"),
        consent_checker=AsyncMock(return_value=True),
    )


def _mock_db() -> AsyncMock:
    db = AsyncMock()

    def _add_with_id(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid4()

    db.add = MagicMock(side_effect=_add_with_id)
    db.flush = AsyncMock()
    return db


class TestSuccessPath:
    async def test_successful_run_returns_completed(self):
        async def _noop_workflow(ctx: PackContext) -> None:
            await ctx.produce_card("follow_up_suggestion", {"name": "Alice"})

        manifest = _manifest()
        runner = PackRunner(
            manifest_loader=_loader(manifest),
            context_factory=_factory(),
            workflows={"daily": _noop_workflow},
        )
        db = _mock_db()
        with patch("api.services.pack.pack_runner.audit", MagicMock(log_event=AsyncMock())):
            result = await runner.run(
                pack_id="testpack",
                workflow_name="daily",
                workspace_id=uuid4(),
                trigger="daily_6am",
                db=db,
            )
        assert result.state == "completed"
        assert result.cards_produced == 1
        assert result.duration_ms >= 0
        assert result.error is None


class TestTimeoutPath:
    async def test_timeout_sets_state_and_discards_cards(self):
        async def _slow(ctx: PackContext) -> None:
            await ctx.produce_card("follow_up_suggestion", {"x": 1})
            await asyncio.sleep(999)

        manifest = _manifest(max_execution_time=1)
        runner = PackRunner(
            manifest_loader=_loader(manifest),
            context_factory=_factory(),
            workflows={"daily": _slow},
        )
        with patch("api.services.pack.pack_runner.audit", MagicMock(log_event=AsyncMock())):
            result = await runner.run(
                pack_id="testpack",
                workflow_name="daily",
                workspace_id=uuid4(),
                trigger="daily",
                db=_mock_db(),
            )
        assert result.state == "timeout"
        assert result.cards_produced == 0
        assert "timed out" in (result.error or "")


class TestErrorPath:
    async def test_exception_sets_state_and_captures_message(self):
        async def _boom(ctx: PackContext) -> None:
            raise RuntimeError("something broke")

        manifest = _manifest()
        runner = PackRunner(
            manifest_loader=_loader(manifest),
            context_factory=_factory(),
            workflows={"daily": _boom},
        )
        with patch("api.services.pack.pack_runner.audit", MagicMock(log_event=AsyncMock())):
            result = await runner.run(
                pack_id="testpack",
                workflow_name="daily",
                workspace_id=uuid4(),
                trigger="daily",
                db=_mock_db(),
            )
        assert result.state == "failed"
        assert "something broke" in (result.error or "")
        assert result.cards_produced == 0


class TestCardSizeRejection:
    async def test_oversized_card_payload_is_dropped(self):
        async def _big_card(ctx: PackContext) -> None:
            # Use numeric values (not strings) so the sanitizer
            # doesn't truncate them; 10k entries × ~8 bytes each
            # exceeds the 64 KB limit.
            await ctx.produce_card(
                "follow_up_suggestion",
                {f"k{i}": i for i in range(10_000)},
            )

        manifest = _manifest()
        runner = PackRunner(
            manifest_loader=_loader(manifest),
            context_factory=_factory(),
            workflows={"daily": _big_card},
        )
        with patch("api.services.pack.pack_runner.audit", MagicMock(log_event=AsyncMock())):
            result = await runner.run(
                pack_id="testpack",
                workflow_name="daily",
                workspace_id=uuid4(),
                trigger="daily",
                db=_mock_db(),
            )
        assert result.state == "completed"
        assert result.cards_produced == 0


class TestLlmQuotaTracking:
    async def test_llm_calls_counted_in_result(self):
        async def _chatty(ctx: PackContext) -> None:
            await ctx.ask_llm("q1")
            await ctx.ask_llm("q2")

        manifest = _manifest(max_llm_calls=3)
        runner = PackRunner(
            manifest_loader=_loader(manifest),
            context_factory=_factory(),
            workflows={"daily": _chatty},
        )
        with patch("api.services.pack.pack_runner.audit", MagicMock(log_event=AsyncMock())):
            result = await runner.run(
                pack_id="testpack",
                workflow_name="daily",
                workspace_id=uuid4(),
                trigger="daily",
                db=_mock_db(),
            )
        assert result.state == "completed"
        assert result.llm_calls_used == 2


class TestUnknownPackOrWorkflow:
    async def test_unknown_pack_raises(self):
        runner = PackRunner(
            manifest_loader=ManifestLoader(packs_dir="/dev/null"),
            context_factory=_factory(),
            workflows={},
        )
        from api.errors import PackNotFoundError

        with pytest.raises(PackNotFoundError):
            await runner.run(
                pack_id="nope",
                workflow_name="daily",
                workspace_id=uuid4(),
                trigger="manual",
                db=_mock_db(),
            )

    async def test_unknown_workflow_raises(self):
        manifest = _manifest()
        runner = PackRunner(
            manifest_loader=_loader(manifest),
            context_factory=_factory(),
            workflows={},
        )
        from api.errors import PackNotFoundError

        with pytest.raises(PackNotFoundError):
            await runner.run(
                pack_id="testpack",
                workflow_name="nonexistent",
                workspace_id=uuid4(),
                trigger="manual",
                db=_mock_db(),
            )


class TestDegradedCapabilities:
    async def test_degraded_caps_reported_in_result(self):
        manifest = PackManifest(
            pack_id="testpack",
            name="Test",
            version="1.0.0",
            description="test",
            author="test",
            capabilities=[
                "read:contacts",
                "read:trusted_persons",
                "query:graph",
            ],
            resource_limits=ResourceLimits(
                max_execution_time_seconds=5,
                max_memory_mb=64,
                max_llm_calls_per_run=1,
            ),
            card_types=["follow_up_suggestion"],
            schedule=ScheduleConfig(),
        )
        factory = PackContextFactory(
            llm_callable=AsyncMock(return_value=""),
            consent_checker=AsyncMock(return_value=False),
        )

        async def _noop(ctx: PackContext) -> None:
            pass

        runner = PackRunner(
            manifest_loader=_loader(manifest),
            context_factory=factory,
            workflows={"daily": _noop},
        )
        with patch("api.services.pack.pack_runner.audit", MagicMock(log_event=AsyncMock())):
            result = await runner.run(
                pack_id="testpack",
                workflow_name="daily",
                workspace_id=uuid4(),
                trigger="daily",
                db=_mock_db(),
            )
        assert result.state == "completed"
        assert "query:graph" in result.degraded_capabilities
        assert "read:trusted_persons" in result.degraded_capabilities
        assert "read:contacts" not in result.degraded_capabilities
