"""Unit tests for the PLA pack flag gate (S14-001)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from api.services import flags

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _call_pla_active(enabled_flags: set[str], face_pipeline_result: bool) -> bool:
    """Invoke ``pla_active`` with patched flag set + patched
    ``face_pipeline_active`` result. Returns whatever the helper
    resolves to."""
    ws = uuid4()
    with (
        patch.object(flags, "_ENABLED_FLAGS", set(enabled_flags)),
        patch.object(
            flags,
            "face_pipeline_active",
            AsyncMock(return_value=face_pipeline_result),
        ),
    ):
        return await flags.pla_active(ws, db=None)  # type: ignore[arg-type]


class TestPlaActive:
    async def test_returns_false_when_pla_flag_off(self):
        result = await _call_pla_active(
            enabled_flags={"face_clustering_enabled"},
            face_pipeline_result=True,
        )
        assert result is False

    async def test_returns_false_when_face_flag_off(self):
        # PLA flag is set but the face flag isn't — PLA needs people
        # data so the helper must refuse.
        result = await _call_pla_active(
            enabled_flags={"pla_pack_enabled"},
            face_pipeline_result=True,
        )
        assert result is False

    async def test_returns_false_when_face_pipeline_inactive(self):
        # Both flags are set but the face pipeline's three-way gate
        # (consent + key) is off.
        result = await _call_pla_active(
            enabled_flags={"pla_pack_enabled", "face_clustering_enabled"},
            face_pipeline_result=False,
        )
        assert result is False

    async def test_returns_true_when_all_gates_open(self):
        result = await _call_pla_active(
            enabled_flags={"pla_pack_enabled", "face_clustering_enabled"},
            face_pipeline_result=True,
        )
        assert result is True


@pytest.mark.asyncio(loop_scope="session")
class TestFlagRegistry:
    async def test_pla_flags_registered(self):
        for key in (
            "pla_pack_enabled",
            "pla_follow_ups_enabled",
            "pla_weekly_summary_enabled",
            "pla_relationship_reminders_enabled",
        ):
            assert key in flags.FLAG_REGISTRY
            assert flags.FLAG_REGISTRY[key].phase == 3

    async def test_pla_pack_is_workspace_scope_and_defaults_off(self):
        defn = flags.FLAG_REGISTRY["pla_pack_enabled"]
        assert defn.scope == "workspace"
        assert defn.default is False

    async def test_pla_sub_flags_are_user_scope_and_default_on(self):
        for key in (
            "pla_follow_ups_enabled",
            "pla_weekly_summary_enabled",
            "pla_relationship_reminders_enabled",
        ):
            defn = flags.FLAG_REGISTRY[key]
            assert defn.scope == "user"
            assert defn.default is True
