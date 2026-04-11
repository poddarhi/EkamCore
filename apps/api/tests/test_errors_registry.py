"""Tests for S10-002: Error registry completeness.

Verifies that every error_code used in the codebase is defined in the
canonical errors_registry, and that the registry entries are well-formed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.errors_registry import ERROR_CODES


# ── Helpers ──

_API_DIR = Path(__file__).resolve().parent.parent / "api"
_ERROR_CODE_RE = re.compile(r'error_code\s*=\s*"([A-Z_]+)"')


def _find_used_error_codes() -> set[str]:
    """Scan all .py files in api/ for error_code="..." assignments."""
    codes: set[str] = set()
    for py_file in _API_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        text = py_file.read_text()
        codes.update(_ERROR_CODE_RE.findall(text))
    return codes


# ── Tests ──


def test_every_used_code_is_in_registry():
    """Every error_code="..." in the codebase must be defined in ERROR_CODES."""
    used = _find_used_error_codes()
    registered = set(ERROR_CODES.keys())
    missing = used - registered
    assert missing == set(), f"Error codes used in code but missing from registry: {missing}"


def test_registry_entries_are_well_formed():
    """Every registry entry must have status, message, and category."""
    for code, entry in ERROR_CODES.items():
        assert "status" in entry, f"{code} missing 'status'"
        assert "message" in entry, f"{code} missing 'message'"
        assert "category" in entry, f"{code} missing 'category'"
        assert isinstance(entry["status"], int), f"{code}.status must be int"
        assert 100 <= entry["status"] < 600, f"{code}.status {entry['status']} out of HTTP range"
        assert len(entry["message"]) > 0, f"{code}.message is empty"
        assert entry["category"] in ("auth", "validation", "resource", "service", "internal"), \
            f"{code}.category '{entry['category']}' not recognized"


def test_no_duplicate_messages():
    """No two different error codes should have identical messages.
    (They can be similar, but exact duplicates suggest a copy-paste error.)
    """
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for code, entry in ERROR_CODES.items():
        msg = entry["message"]
        if msg in seen:
            duplicates.append(f"{code} duplicates {seen[msg]}: '{msg}'")
        else:
            seen[msg] = code

    assert duplicates == [], f"Duplicate messages: {duplicates}"
