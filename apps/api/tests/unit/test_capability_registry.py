"""Unit tests for the pack capability registry (S14-002)."""

from __future__ import annotations

import pytest

from api.services.pack.capability_registry import (
    CAPABILITY_REGISTRY,
    CapabilityDef,
    consent_gated_capabilities,
    get,
)


class TestRegistryShape:
    @pytest.mark.parametrize(
        "name",
        [
            "read:contacts",
            "read:calendar_events",
            "read:reminders",
            "read:trusted_persons",
            "read:graph_edges",
            "read:files",
            "read:photos",
            "write:reminders",
            "query:graph",
            "invoke:llm",
        ],
    )
    def test_required_capability_registered(self, name: str):
        defn = CAPABILITY_REGISTRY[name]
        assert isinstance(defn, CapabilityDef)
        assert defn.name == name
        assert defn.data_scope in ("read", "write", "query", "invoke")

    def test_get_returns_none_for_unknown(self):
        assert get("read:nonexistent") is None
        assert get("delete:all_the_things") is None


class TestConsentGating:
    def test_trusted_persons_requires_consent(self):
        assert CAPABILITY_REGISTRY["read:trusted_persons"].requires_consent is True

    def test_graph_edges_requires_consent(self):
        assert CAPABILITY_REGISTRY["read:graph_edges"].requires_consent is True

    def test_query_graph_requires_consent(self):
        assert CAPABILITY_REGISTRY["query:graph"].requires_consent is True

    def test_contacts_does_not_require_consent(self):
        assert CAPABILITY_REGISTRY["read:contacts"].requires_consent is False

    def test_llm_does_not_require_consent(self):
        assert CAPABILITY_REGISTRY["invoke:llm"].requires_consent is False

    def test_consent_gated_set_matches_individual_flags(self):
        gated = consent_gated_capabilities()
        assert "read:trusted_persons" in gated
        assert "read:graph_edges" in gated
        assert "query:graph" in gated
        assert "read:contacts" not in gated
        assert "invoke:llm" not in gated


class TestWriteCapabilityIsolation:
    def test_only_one_write_capability(self):
        writes = [
            name
            for name, defn in CAPABILITY_REGISTRY.items()
            if defn.data_scope == "write"
        ]
        assert writes == ["write:reminders"], (
            "The capability registry intentionally exposes exactly one "
            "write capability. Adding new writes requires a security review."
        )
