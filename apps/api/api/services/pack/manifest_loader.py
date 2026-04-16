"""Pack manifest loader (S14-002 / ART-13 §3, ART-14).

Walks a ``packs/`` directory, parses each ``manifest.yaml`` via
``yaml.safe_load`` (NEVER ``yaml.load`` — see ART-14 threat model
§2.3), validates the result against the ``PackManifest`` Pydantic
model, cross-checks capabilities against
``capability_registry.CAPABILITY_REGISTRY``, and registers the
valid ones.

Packs that fail validation are logged at WARNING and **skipped** —
a malformed pack must never crash API startup. The loader keeps
a ``load_errors`` list so admin endpoints can surface the failure
reason without digging through logs.

Validation rules (ART-13 §3):

- ``pack_id`` — alphanumeric + underscore, max 64 chars.
- ``version`` — SemVer (``MAJOR.MINOR.PATCH`` with optional
  pre-release / build suffix).
- ``capabilities`` — every entry must be a known capability name
  in the registry.
- ``resource_limits`` — all positive; caps at 600s execution,
  1024 MB memory, 20 LLM calls per run.
- ``card_types`` — alphanumeric + underscore, max 64 chars each.
- ``schedule.daily`` — ``HH:MM`` 24-hour or null.
- ``schedule.weekly`` — ``"<day> HH:MM"`` (day = monday..sunday)
  or null.

PII rule: never log manifest file contents beyond the pack id and
error message. Manifest author fields are safe to log since they
are configured per deployment.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field, field_validator

from api.services.pack.capability_registry import CAPABILITY_REGISTRY

logger = structlog.get_logger()


_PACK_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_CARD_TYPE_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_WEEKLY_RE = re.compile(
    r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"\s+([01]\d|2[0-3]):[0-5]\d$"
)


# ── Pydantic models ───────────────────────────────────────────────────────


class ResourceLimits(BaseModel):
    max_execution_time_seconds: int = Field(gt=0, le=600)
    max_memory_mb: int = Field(gt=0, le=1024)
    max_llm_calls_per_run: int = Field(gt=0, le=20)


class ScheduleConfig(BaseModel):
    daily: str | None = None
    weekly: str | None = None

    @field_validator("daily")
    @classmethod
    def _validate_daily(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _HHMM_RE.fullmatch(v):
            raise ValueError("daily must be HH:MM (24h) or null")
        return v

    @field_validator("weekly")
    @classmethod
    def _validate_weekly(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _WEEKLY_RE.fullmatch(v):
            raise ValueError(
                "weekly must be '<day> HH:MM' (day = monday..sunday) or null"
            )
        return v


class PackManifest(BaseModel):
    pack_id: str
    name: str = Field(min_length=1, max_length=255)
    version: str
    description: str = Field(min_length=1, max_length=1000)
    author: str = Field(min_length=1, max_length=255)
    capabilities: list[str] = Field(min_length=1)
    resource_limits: ResourceLimits
    card_types: list[str] = Field(min_length=1)
    schedule: ScheduleConfig

    @field_validator("pack_id")
    @classmethod
    def _validate_pack_id(cls, v: str) -> str:
        if not _PACK_ID_RE.fullmatch(v):
            raise ValueError(
                "pack_id must be alphanumeric + underscore, max 64 chars"
            )
        return v

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not _SEMVER_RE.fullmatch(v):
            raise ValueError("version must be SemVer (MAJOR.MINOR.PATCH)")
        return v

    @field_validator("card_types")
    @classmethod
    def _validate_card_types(cls, v: list[str]) -> list[str]:
        for ct in v:
            if not _CARD_TYPE_RE.fullmatch(ct):
                raise ValueError(
                    f"card_type '{ct}' must be alphanumeric + underscore, "
                    "max 64 chars"
                )
        return v


# ── Loader ────────────────────────────────────────────────────────────────


class ManifestLoadError(Exception):
    """Raised internally when a single manifest fails validation.
    Never escapes ``load_all`` — the loader catches these and
    records them in ``load_errors``."""


class ManifestLoader:
    """Walk a packs directory, parse + validate every ``manifest.yaml``,
    and keep the valid results in memory.

    Usage:
        loader = ManifestLoader("packs")
        loader.load_all()
        pla = loader.get("pla")
    """

    def __init__(self, packs_dir: str | Path = "packs") -> None:
        self._packs_dir = Path(packs_dir)
        self._manifests: dict[str, PackManifest] = {}
        self._load_errors: list[dict[str, str]] = []

    # -- public api --

    @property
    def manifests(self) -> dict[str, PackManifest]:
        return dict(self._manifests)

    @property
    def load_errors(self) -> list[dict[str, str]]:
        return list(self._load_errors)

    def get(self, pack_id: str) -> PackManifest | None:
        return self._manifests.get(pack_id)

    def load_all(self) -> dict[str, PackManifest]:
        """Load every pack in ``packs_dir``.

        Returns the map of pack_id → PackManifest for the
        successfully-loaded packs. Errors are appended to
        ``load_errors`` and logged at WARNING; they never raise.
        """
        self._manifests.clear()
        self._load_errors.clear()

        if not self._packs_dir.exists():
            logger.info(
                "pack_loader_no_packs_dir",
                packs_dir=str(self._packs_dir),
            )
            return {}

        for entry in sorted(self._packs_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.yaml"
            if not manifest_path.exists():
                continue
            try:
                manifest = self._load_one(manifest_path)
            except ManifestLoadError as exc:
                self._load_errors.append(
                    {"path": str(manifest_path), "error": str(exc)}
                )
                logger.warning(
                    "pack_manifest_invalid",
                    path=str(manifest_path),
                    error=str(exc),
                )
                continue
            if manifest.pack_id in self._manifests:
                self._load_errors.append(
                    {
                        "path": str(manifest_path),
                        "error": f"duplicate pack_id '{manifest.pack_id}'",
                    }
                )
                logger.warning(
                    "pack_manifest_duplicate_pack_id",
                    pack_id=manifest.pack_id,
                    path=str(manifest_path),
                )
                continue
            self._manifests[manifest.pack_id] = manifest
            logger.info(
                "pack_manifest_loaded",
                pack_id=manifest.pack_id,
                version=manifest.version,
                capabilities=len(manifest.capabilities),
            )

        return dict(self._manifests)

    def validate(self, manifest: PackManifest) -> list[str]:
        """Return a list of post-parse validation errors.

        Returns an empty list when the manifest is fully valid.
        The checks here are the cross-field rules that Pydantic
        can't express on its own — primarily "does every capability
        resolve against the registry?" — plus a safety net in case
        a caller hands in a manifest built programmatically rather
        than via ``load_all``.
        """
        errors: list[str] = []
        for cap in manifest.capabilities:
            if CAPABILITY_REGISTRY.get(cap) is None:
                errors.append(f"unknown capability '{cap}'")
        return errors

    # -- internals --

    def _load_one(self, path: Path) -> PackManifest:
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestLoadError(f"read failed: {exc}") from exc

        try:
            # NEVER yaml.load — see ART-14 §2.3.
            data: Any = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ManifestLoadError(f"yaml parse failed: {exc}") from exc

        if not isinstance(data, dict):
            raise ManifestLoadError(
                "manifest must be a YAML mapping at the top level"
            )

        try:
            manifest = PackManifest.model_validate(data)
        except Exception as exc:
            raise ManifestLoadError(f"schema validation failed: {exc}") from exc

        cross_errors = self.validate(manifest)
        if cross_errors:
            raise ManifestLoadError(
                "capability validation failed: " + "; ".join(cross_errors)
            )

        return manifest
