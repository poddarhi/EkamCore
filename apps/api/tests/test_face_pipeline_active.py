"""Tests for face_pipeline_active (S11-001).

Verifies all 4 combinations of flag / consent / key state and that the
function is the single source of truth for the Phase 3 face gate.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from api.services import flags
from api.services.flags import face_pipeline_active, is_flag_enabled
from api.services.settings_service import set_setting


@pytest.fixture
def workspace_id(seed_user):
    return seed_user["workspace_id"]


# ── Unit: is_flag_enabled ──────────────────────────────────────────────────


class TestIsFlagEnabled:
    def test_known_flag_not_in_active_set_returns_false(self):
        """face_clustering_enabled is known but default-off."""
        assert is_flag_enabled("face_clustering_enabled") is False

    def test_unknown_flag_returns_false(self):
        assert is_flag_enabled("nonexistent_flag") is False

    def test_known_flag_in_active_set_returns_true(self):
        """When the flag is activated in _ENABLED_FLAGS, returns True."""
        with patch.object(
            flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}
        ):
            assert is_flag_enabled("face_clustering_enabled") is True


# ── face_pipeline_active: all 4 gates ─────────────────────────────────────


@pytest.mark.asyncio
class TestFacePipelineActive:
    async def test_all_off_returns_false(
        self, test_session_factory, workspace_id
    ):
        """Default state: flag off, no consent, no key."""
        with patch.object(flags, "_ENABLED_FLAGS", set()), patch.object(
            flags.settings, "FACE_EMBED_KEY", ""
        ):
            async with test_session_factory() as db:
                result = await face_pipeline_active(workspace_id, db)
        assert result is False

    async def test_flag_on_consent_off_returns_false(
        self, test_session_factory, workspace_id
    ):
        with patch.object(
            flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}
        ), patch.object(
            flags.settings, "FACE_EMBED_KEY", "x" * 44  # placeholder, not validated here
        ):
            async with test_session_factory() as db:
                result = await face_pipeline_active(workspace_id, db)
        assert result is False

    async def test_flag_off_consent_on_returns_false(
        self, test_session_factory, workspace_id
    ):
        # Set consent to true
        async with test_session_factory() as db:
            await set_setting(
                key="face_clustering_consent",
                value=True,
                user_id=workspace_id,  # ignored for workspace-scoped
                workspace_id=workspace_id,
                db=db,
            )
            await db.commit()

        # Flag off
        with patch.object(flags, "_ENABLED_FLAGS", set()), patch.object(
            flags.settings, "FACE_EMBED_KEY", "x" * 44
        ):
            async with test_session_factory() as db:
                result = await face_pipeline_active(workspace_id, db)
        assert result is False

    async def test_key_missing_returns_false_even_with_flag_and_consent(
        self, test_session_factory, workspace_id
    ):
        async with test_session_factory() as db:
            await set_setting(
                key="face_clustering_consent",
                value=True,
                user_id=workspace_id,
                workspace_id=workspace_id,
                db=db,
            )
            await db.commit()

        with patch.object(
            flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}
        ), patch.object(flags.settings, "FACE_EMBED_KEY", ""):
            async with test_session_factory() as db:
                result = await face_pipeline_active(workspace_id, db)
        assert result is False

    async def test_all_three_gates_on_returns_true(
        self, test_session_factory, workspace_id
    ):
        # Set consent
        async with test_session_factory() as db:
            await set_setting(
                key="face_clustering_consent",
                value=True,
                user_id=workspace_id,
                workspace_id=workspace_id,
                db=db,
            )
            await db.commit()

        with patch.object(
            flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}
        ), patch.object(flags.settings, "FACE_EMBED_KEY", "x" * 44):
            async with test_session_factory() as db:
                result = await face_pipeline_active(workspace_id, db)
        assert result is True

    async def test_workspace_isolation(
        self, test_session_factory, workspace_id
    ):
        """Consent in workspace A does not activate the pipeline for workspace B."""
        other_ws = uuid4()

        # Grant consent only to workspace_id
        async with test_session_factory() as db:
            await set_setting(
                key="face_clustering_consent",
                value=True,
                user_id=workspace_id,
                workspace_id=workspace_id,
                db=db,
            )
            await db.commit()

        with patch.object(
            flags, "_ENABLED_FLAGS", {"face_clustering_enabled"}
        ), patch.object(flags.settings, "FACE_EMBED_KEY", "x" * 44):
            async with test_session_factory() as db:
                # Workspace A (consented): active
                active_a = await face_pipeline_active(workspace_id, db)
                # Workspace B (not consented): NOT active
                active_b = await face_pipeline_active(other_ws, db)

        assert active_a is True
        assert active_b is False
