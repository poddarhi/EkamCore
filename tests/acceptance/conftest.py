"""Shared fixtures for acceptance tests (G-01 / ART-02).

Re-exports the core test infrastructure from apps/api/tests/conftest.py
so acceptance tests can use the same DB session, client, seed_user, and
auth_tokens fixtures.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make the api package importable
API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

# Re-export all fixtures from the main test conftest
from tests.conftest import (  # noqa: F401, E402
    client,
    db,
    test_session_factory,
    seed_user,
    auth_tokens,
    mock_rate_limiter_redis,
)

# ── Acceptance report collector ─────────────────────────────────────────────

REPORT_PATH = Path(__file__).resolve().parents[2] / "acceptance_report.json"

_results: list[dict] = []


def record_result(
    story_id: str,
    criteria: str,
    passed: bool,
    details: str = "",
) -> None:
    """Append a single acceptance criterion result."""
    _results.append({
        "story_id": story_id,
        "criteria": criteria,
        "result": "PASS" if passed else "FAIL",
        "details": details,
    })


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Record acceptance results for tests that fail before reaching
    the explicit record_result() call (e.g. assertion failures).

    Tests that pass will have already called record_result() explicitly,
    so we only record here on failure to avoid duplicates.
    """
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    markers = list(item.iter_markers("acceptance"))
    if not markers:
        return
    if rep.failed:
        marker = markers[0]
        story_id = marker.kwargs.get("story_id", "")
        criteria = marker.kwargs.get("criteria", item.name)
        record_result(story_id, criteria, False, str(rep.longrepr)[:200])


def pytest_sessionfinish(session, exitstatus):
    """Write the acceptance report JSON at the end of the test session."""
    if not _results:
        return
    total = len(_results)
    passed = sum(1 for r in _results if r["result"] == "PASS")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
        "results": _results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
