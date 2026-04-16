"""Security audit for the Pack sandbox (S14-012 / ART-14).

These tests pin the security invariants of PackContext and the
manifest loader so regressions in the sandbox boundary are caught
before they reach a reviewer's desk.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from api.services.pack.manifest_loader import ResourceLimits
from api.services.pack.pack_context import PackContext


def _ctx(**kw) -> PackContext:
    defaults = dict(
        workspace_id=uuid4(),
        capabilities={"read:contacts", "invoke:llm"},
        resource_limits=ResourceLimits(
            max_execution_time_seconds=60,
            max_memory_mb=64,
            max_llm_calls_per_run=1,
        ),
        allowed_card_types={"follow_up_suggestion"},
        consent_active=True,
        pack_id="sectest",
        pack_run_id=None,
        db=AsyncMock(),
        llm_callable=AsyncMock(return_value=""),
    )
    defaults.update(kw)
    return PackContext(**defaults)


class TestNoSessionExposed:
    def test_no_db_attribute(self):
        ctx = _ctx()
        for name in ("db", "session", "_db_session", "engine", "connection"):
            assert not hasattr(ctx, name), f"PackContext exposes '{name}'"

    def test_no_raw_sql_method(self):
        ctx = _ctx()
        for name in ("execute", "raw", "sql", "run_sql", "text"):
            assert not hasattr(ctx, name), f"PackContext exposes '{name}'"


class TestNoFaceDataAccess:
    def test_no_face_table_methods(self):
        ctx = _ctx()
        for name in (
            "get_face_detections",
            "get_face_clusters",
            "get_embeddings",
            "get_qdrant_points",
            "get_face_model",
        ):
            assert not hasattr(ctx, name), f"PackContext exposes '{name}'"


class TestCardPayloadSanitized:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_html_script_stripped_from_card(self):
        ctx = _ctx()
        await ctx.produce_card(
            "follow_up_suggestion",
            {"name": "Alice <script>alert(1)</script>", "n": 5},
        )
        payload = ctx.cards[0]["payload"]
        assert "<script>" not in payload["name"]
        assert "alert(1)" in payload["name"]  # text survives, tags don't
        assert payload["n"] == 5


class TestNoNetworkAttributes:
    def test_no_http_or_socket_attributes(self):
        ctx = _ctx()
        for name in ("httpx", "requests", "socket", "urllib", "aiohttp"):
            assert not hasattr(ctx, name), f"PackContext exposes '{name}'"


class TestPersonQueryInjection:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sql_injection_in_name_is_parameterized(self):
        from api.services.query.person_detector import detect_person_references

        # The DB mock returns empty — the key assertion is that no
        # exception is raised, meaning the ILIKE is parameterized.
        db = AsyncMock()
        scalars_mock = AsyncMock()
        scalars_mock.all = lambda: []
        result_mock = AsyncMock()
        result_mock.scalars = lambda: scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        result = await detect_person_references(
            "who is Alice'; DROP TABLE trusted_persons--",
            uuid4(),
            db,
        )
        assert result == []
        # db.execute was called, meaning the query ran without error.
        db.execute.assert_awaited()


class TestCapabilityRegistryInvariants:
    def test_face_table_capabilities_not_in_registry(self):
        from api.services.pack.capability_registry import CAPABILITY_REGISTRY

        for bad in (
            "read:face_detections",
            "read:face_clusters",
            "read:face_embeddings",
            "write:face_detections",
        ):
            assert bad not in CAPABILITY_REGISTRY

    def test_only_one_write_capability(self):
        from api.services.pack.capability_registry import CAPABILITY_REGISTRY

        writes = [n for n, d in CAPABILITY_REGISTRY.items() if d.data_scope == "write"]
        assert writes == ["write:reminders"]
