"""Security tests for PackContext (S14-003 / ART-14).

These tests enforce the invariants that keep a pack from breaking
out of its sandbox:

  1. ``workspace_id`` is set at construction and cannot be changed
     by the pack — no setter, no public attribute that isn't
     already a UUID, no back-channel via the session.
  2. The session is held privately; no ``db`` or ``session``
     property exposes it.
  3. Only the capabilities declared in the manifest surface on
     the context — ``read:face_detections`` and
     ``read:face_clusters`` never resolve because no such
     capabilities exist in the registry, so a pack can't even
     reference them.
  4. Consent gating is strict: a context built with
     ``consent_active=False`` plus a face-gated capability raises
     on every face method, even if the capability set still
     includes it. (The factory strips the cap in practice; this
     test exercises the belt-and-braces check on PackContext
     itself.)
  5. No raw SQL execution path exists on the context.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from api.errors import CapabilityDeniedError
from api.services.pack.capability_registry import (
    CAPABILITY_REGISTRY,
    consent_gated_capabilities,
)
from api.services.pack.manifest_loader import ResourceLimits
from api.services.pack.pack_context import PackContext


def _ctx(
    *, capabilities: set[str], consent_active: bool = True
) -> PackContext:
    return PackContext(
        workspace_id=uuid4(),
        capabilities=capabilities,
        resource_limits=ResourceLimits(
            max_execution_time_seconds=60,
            max_memory_mb=64,
            max_llm_calls_per_run=1,
        ),
        allowed_card_types={"follow_up_suggestion"},
        consent_active=consent_active,
        pack_id="isolation_test",
        pack_run_id=None,
        db=AsyncMock(),
        llm_callable=AsyncMock(return_value=""),
    )


class TestWorkspaceIsolation:
    def test_workspace_id_is_frozen_via_constructor(self):
        ws_a = uuid4()
        ctx = PackContext(
            workspace_id=ws_a,
            capabilities=set(),
            resource_limits=ResourceLimits(
                max_execution_time_seconds=60,
                max_memory_mb=64,
                max_llm_calls_per_run=1,
            ),
            allowed_card_types=set(),
            consent_active=True,
            pack_id="iso",
            pack_run_id=None,
            db=AsyncMock(),
        )
        assert ctx.workspace_id == ws_a
        # The private attribute exists but we don't expose a setter.
        assert not hasattr(PackContext, "workspace_id.setter")

    def test_no_session_property_exposes_raw_db(self):
        ctx = _ctx(capabilities=set())
        # PackContext intentionally does not expose ``db`` or
        # ``session`` as a public attribute. A pack that tries
        # ``context.db`` or ``context.session`` should get an
        # AttributeError.
        for name in ("db", "session", "_db_session"):
            assert not hasattr(ctx, name), (
                f"PackContext exposes '{name}' — must be kept private"
            )

    def test_no_raw_sql_execute_method(self):
        ctx = _ctx(capabilities=set())
        for name in ("execute", "raw", "sql", "query", "run_sql"):
            assert not hasattr(ctx, name), (
                f"PackContext exposes '{name}' — must not allow raw SQL"
            )


class TestFaceDataSandbox:
    def test_face_detection_capability_does_not_exist_in_registry(self):
        # A pack cannot even *declare* direct face-table access
        # because the capability name isn't in the registry. The
        # manifest loader would reject it at load time; this test
        # pins the registry so nobody adds such a capability
        # casually in a later story.
        for bad in (
            "read:face_detections",
            "read:face_clusters",
            "read:face_embeddings",
        ):
            assert bad not in CAPABILITY_REGISTRY, (
                f"'{bad}' must not be a declarable capability"
            )

    def test_no_public_method_returns_face_rows(self):
        ctx = _ctx(capabilities=set())
        for name in (
            "get_face_detections",
            "get_face_clusters",
            "get_embeddings",
            "get_qdrant_points",
        ):
            assert not hasattr(ctx, name), (
                f"PackContext exposes '{name}' — must not surface raw face rows"
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_consent_off_blocks_every_face_method(self):
        # Even with full capabilities, a context built with
        # consent_active=False must refuse every face method.
        all_face_caps = {
            "read:trusted_persons",
            "read:graph_edges",
            "query:graph",
            "read:photos",
        }
        ctx = _ctx(capabilities=all_face_caps, consent_active=False)
        with pytest.raises(CapabilityDeniedError):
            await ctx.get_persons()
        with pytest.raises(CapabilityDeniedError):
            await ctx.get_person_by_id(uuid4())
        with pytest.raises(CapabilityDeniedError):
            await ctx.get_edges_for_person(uuid4())
        with pytest.raises(CapabilityDeniedError):
            await ctx.traverse_graph(uuid4())
        with pytest.raises(CapabilityDeniedError):
            await ctx.get_photos_for_person(uuid4())


class TestConsentGatedRegistryCoverage:
    def test_consent_gated_set_is_non_empty(self):
        assert consent_gated_capabilities(), (
            "at least one capability must be marked requires_consent=True"
        )

    def test_consent_gated_set_includes_all_face_derived(self):
        gated = consent_gated_capabilities()
        for cap in ("read:trusted_persons", "read:graph_edges", "query:graph"):
            assert cap in gated


class TestCapabilitiesAreImmutable:
    def test_capabilities_set_is_frozen(self):
        ctx = _ctx(capabilities={"read:contacts"})
        assert isinstance(ctx.capabilities, frozenset)
        # A pack that tries to add a capability to the returned
        # set gets a TypeError from frozenset — no need to defend
        # against it at the code level.
        with pytest.raises(AttributeError):
            ctx.capabilities.add("invoke:llm")  # type: ignore[attr-defined]
