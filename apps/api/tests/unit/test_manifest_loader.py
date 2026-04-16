"""Unit tests for the pack manifest loader (S14-002)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from api.services.pack.manifest_loader import (
    ManifestLoader,
    PackManifest,
    ResourceLimits,
    ScheduleConfig,
)


VALID_MANIFEST = dedent(
    """
    pack_id: pla
    name: Personal Life Assistant
    version: 1.0.0
    description: Follow-up suggestions and weekly summaries.
    author: EkamCore
    capabilities:
      - read:contacts
      - read:trusted_persons
      - invoke:llm
    resource_limits:
      max_execution_time_seconds: 300
      max_memory_mb: 512
      max_llm_calls_per_run: 5
    card_types:
      - follow_up_suggestion
      - weekly_summary
    schedule:
      daily: "06:00"
      weekly: "monday 08:00"
    """
).strip()


def _write_manifest(base: Path, pack_id: str, yaml_text: str) -> Path:
    pack_dir = base / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    path = pack_dir / "manifest.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


class TestValidManifest:
    def test_loads_pla_manifest_from_disk(self, tmp_path):
        _write_manifest(tmp_path, "pla", VALID_MANIFEST)
        loader = ManifestLoader(packs_dir=tmp_path)
        result = loader.load_all()
        assert "pla" in result
        pla = result["pla"]
        assert isinstance(pla, PackManifest)
        assert pla.version == "1.0.0"
        assert pla.resource_limits.max_llm_calls_per_run == 5
        assert pla.schedule.daily == "06:00"
        assert pla.schedule.weekly == "monday 08:00"
        assert loader.load_errors == []

    def test_loads_real_repo_pla_manifest(self):
        # S14-002 committed ``packs/pla/manifest.yaml`` at the repo
        # root. The loader should pick it up without modification.
        # Path walk: tests/unit/test_manifest_loader.py
        #   parents[0]=unit, [1]=tests, [2]=api, [3]=apps, [4]=repo root.
        repo_root = Path(__file__).resolve().parents[4]
        loader = ManifestLoader(packs_dir=repo_root / "packs")
        loader.load_all()
        assert "pla" in loader.manifests, (
            f"expected pla in {loader.manifests}, "
            f"errors={loader.load_errors}"
        )
        pla = loader.manifests["pla"]
        assert pla.pack_id == "pla"
        assert "invoke:llm" in pla.capabilities


class TestValidationErrors:
    def test_missing_required_field_is_logged_and_skipped(self, tmp_path):
        _write_manifest(
            tmp_path,
            "broken",
            dedent(
                """
                pack_id: broken
                name: Broken
                version: 1.0.0
                description: missing author
                capabilities: [read:contacts]
                resource_limits:
                  max_execution_time_seconds: 60
                  max_memory_mb: 64
                  max_llm_calls_per_run: 1
                card_types: [x]
                schedule: {}
                """
            ).strip(),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "broken" not in loader.manifests
        assert len(loader.load_errors) == 1

    def test_unknown_capability_is_rejected(self, tmp_path):
        _write_manifest(
            tmp_path,
            "bad_cap",
            VALID_MANIFEST.replace(
                "- invoke:llm", "- invoke:llm\n  - delete:everything"
            ),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "bad_cap" not in loader.manifests
        assert any(
            "unknown capability" in err["error"]
            for err in loader.load_errors
        )

    def test_negative_resource_limit_is_rejected(self, tmp_path):
        _write_manifest(
            tmp_path,
            "negative",
            VALID_MANIFEST.replace(
                "max_memory_mb: 512", "max_memory_mb: -1"
            ),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "negative" not in loader.manifests

    def test_resource_limit_above_cap_is_rejected(self, tmp_path):
        _write_manifest(
            tmp_path,
            "too_high",
            VALID_MANIFEST.replace(
                "max_execution_time_seconds: 300",
                "max_execution_time_seconds: 9999",
            ),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "too_high" not in loader.manifests

    def test_bad_pack_id_rejected(self, tmp_path):
        _write_manifest(
            tmp_path,
            "bad_id",
            VALID_MANIFEST.replace("pack_id: pla", "pack_id: has-dash"),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "has-dash" not in loader.manifests

    def test_bad_version_rejected(self, tmp_path):
        _write_manifest(
            tmp_path,
            "bad_version",
            VALID_MANIFEST.replace("version: 1.0.0", "version: v1"),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "pla" not in loader.manifests

    def test_bad_daily_schedule_rejected(self, tmp_path):
        _write_manifest(
            tmp_path,
            "bad_daily",
            VALID_MANIFEST.replace('daily: "06:00"', 'daily: "25:00"'),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "pla" not in loader.manifests

    def test_bad_weekly_schedule_rejected(self, tmp_path):
        _write_manifest(
            tmp_path,
            "bad_weekly",
            VALID_MANIFEST.replace(
                'weekly: "monday 08:00"', 'weekly: "someday 08:00"'
            ),
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert "pla" not in loader.manifests


class TestSafeLoad:
    def test_arbitrary_python_tags_are_rejected(self, tmp_path):
        # A yaml.load caller would happily instantiate arbitrary
        # Python objects via !!python/object/apply. yaml.safe_load
        # raises ConstructorError instead, which our loader turns
        # into a ManifestLoadError.
        _write_manifest(
            tmp_path,
            "dangerous",
            "!!python/object/apply:os.system ['echo pwned']\n",
        )
        loader = ManifestLoader(packs_dir=tmp_path)
        loader.load_all()
        assert loader.manifests == {}
        assert len(loader.load_errors) == 1
        assert "yaml parse failed" in loader.load_errors[0]["error"]


class TestMissingPacksDir:
    def test_no_packs_dir_returns_empty_without_error(self, tmp_path):
        loader = ManifestLoader(packs_dir=tmp_path / "does_not_exist")
        result = loader.load_all()
        assert result == {}
        assert loader.load_errors == []


class TestValidateMethod:
    def test_returns_empty_list_for_valid_manifest(self):
        manifest = PackManifest(
            pack_id="tst",
            name="Test",
            version="1.0.0",
            description="x",
            author="y",
            capabilities=["read:contacts"],
            resource_limits=ResourceLimits(
                max_execution_time_seconds=10,
                max_memory_mb=10,
                max_llm_calls_per_run=1,
            ),
            card_types=["x"],
            schedule=ScheduleConfig(),
        )
        loader = ManifestLoader()
        assert loader.validate(manifest) == []

    def test_flags_unknown_capability_post_parse(self):
        loader = ManifestLoader()
        manifest = PackManifest(
            pack_id="tst",
            name="Test",
            version="1.0.0",
            description="x",
            author="y",
            capabilities=["read:contacts"],
            resource_limits=ResourceLimits(
                max_execution_time_seconds=10,
                max_memory_mb=10,
                max_llm_calls_per_run=1,
            ),
            card_types=["x"],
            schedule=ScheduleConfig(),
        )
        # Bypass model validation to inject an invalid capability
        # so we exercise the cross-field validator directly.
        object.__setattr__(
            manifest, "capabilities", ["read:contacts", "write:everything"]
        )
        errors = loader.validate(manifest)
        assert len(errors) == 1
        assert "write:everything" in errors[0]
