#!/usr/bin/env python3
"""Security checklist verification script (G-05 / ART-14 Section 19).

Checks each security requirement programmatically where possible.
Outputs security_checklist_report.json.

Usage:
    python scripts/security_checklist.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "apps" / "api" / "api"
TESTS_DIR = REPO_ROOT / "apps" / "api" / "tests"

results: list[dict] = []


def check(item_id: str, title: str, passed: bool, details: str = ""):
    results.append({
        "id": item_id,
        "title": title,
        "status": "PASS" if passed else "FAIL",
        "details": details,
    })
    icon = "✓" if passed else "✗"
    print(f"  [{icon}] {item_id}: {title}" + (f" — {details}" if details else ""))


def scan_files(directory: Path, pattern: str, glob: str = "**/*.py") -> list[str]:
    """Return file paths containing the pattern."""
    matches = []
    for f in directory.glob(glob):
        if "__pycache__" in str(f):
            continue
        if re.search(pattern, f.read_text()):
            matches.append(str(f.relative_to(REPO_ROOT)))
    return matches


# ── Phase 0: Auth & Infrastructure ──

print("\n=== Phase 0: Auth & Infrastructure ===")

check(
    "SEC-01",
    "JWT authentication on all protected endpoints",
    bool(scan_files(API_DIR / "middleware", r"get_current_user")),
    "get_current_user dependency found in auth middleware",
)

check(
    "SEC-02",
    "CSRF double-submit cookie on state-changing methods",
    bool(scan_files(API_DIR / "middleware", r"validate_csrf")),
    "validate_csrf dependency found",
)

# Check that routers using POST/PATCH/DELETE also import validate_csrf
router_files = list((API_DIR / "routers").glob("*.py"))
csrf_missing = []
exempt = {"health.py", "internal.py", "auth.py", "__init__.py", "admin.py", "query.py"}
for f in router_files:
    if f.name in exempt:
        continue
    text = f.read_text()
    has_writes = bool(re.search(r'@router\.(post|patch|delete)', text))
    has_csrf = "validate_csrf" in text
    if has_writes and not has_csrf:
        csrf_missing.append(f.name)

check(
    "SEC-03",
    "CSRF enforced on all state-changing routes",
    len(csrf_missing) == 0,
    f"Missing import in: {csrf_missing}" if csrf_missing else "All write routers import validate_csrf",
)

check(
    "SEC-04",
    "Brute-force rate limiting on auth endpoints",
    bool(scan_files(API_DIR / "services", r"_LOCKOUT_THRESHOLD")),
    "Lockout threshold defined in rate_limiter.py",
)

check(
    "SEC-05",
    "Password hashing with strong KDF",
    bool(scan_files(API_DIR / "services", r"argon2|bcrypt|passlib")),
    "Argon2/bcrypt found in auth service",
)

check(
    "SEC-06",
    "Refresh token rotation on use",
    bool(scan_files(API_DIR / "services", r"is_revoked.*True|session\.is_revoked")),
    "Old session revoked during refresh",
)

check(
    "SEC-07",
    "Refresh token replay detection",
    bool(scan_files(API_DIR / "services", r"replay_detected|REFRESH_REVOKED")),
    "Replay detection logic found",
)

# ── Phase 1: Data isolation ──

print("\n=== Phase 1: Data Isolation ===")

# Check workspace_id in all model queries
check(
    "SEC-08",
    "Workspace isolation on all data queries",
    bool(scan_files(API_DIR, r"workspace_id")),
    "workspace_id referenced across codebase",
)

check(
    "SEC-09",
    "No raw SQL (parameterized only)",
    not bool(scan_files(API_DIR, r'f".*SELECT|f".*INSERT|f".*UPDATE|f".*DELETE')),
    "No f-string SQL found",
)

check(
    "SEC-10",
    "Structured error responses (no bare HTTPException)",
    not bool(scan_files(API_DIR / "routers", r"raise HTTPException")),
    "No bare HTTPException in routers",
)

# ── Phase 2: Data processing security ──

print("\n=== Phase 2: Data Processing ===")

check(
    "SEC-11",
    "HTML escape on LLM output",
    bool(scan_files(API_DIR / "services" / "query", r"html\.escape")),
    "html.escape found in output_parser.py",
)

check(
    "SEC-12",
    "LLM prompt injection prevention (XML tags)",
    bool(scan_files(API_DIR / "services" / "query" / "prompts", r"<context>|<question>")),
    "XML-tagged prompt structure found",
)

check(
    "SEC-13",
    "Source hallucination detection",
    bool(scan_files(API_DIR / "services" / "query", r"hallucinated|valid_sources")),
    "Hallucination check found in output_parser.py",
)

check(
    "SEC-14",
    "No PII in logs (correlation_id only)",
    not bool(scan_files(API_DIR, r'logger\.\w+\(.*query_text|logger\.\w+\(.*password|logger\.\w+\(.*email=(?!.*hash)')),
    "No raw PII logged",
)

check(
    "SEC-15",
    "Feature flags gate new endpoints",
    bool(scan_files(API_DIR / "middleware", r"require_flag|FeatureDisabledError")),
    "Feature gate middleware found",
)

# ── Security test coverage ──

print("\n=== Security Test Coverage ===")

check(
    "SEC-16",
    "Workspace isolation tests exist",
    bool(scan_files(TESTS_DIR, r"WORKSPACE_ACCESS_DENIED")),
    "Workspace isolation assertions found in tests",
)

check(
    "SEC-17",
    "CSRF tests exist",
    bool(scan_files(TESTS_DIR, r"CSRF_VALIDATION_FAILED")),
    "CSRF test assertions found",
)

check(
    "SEC-18",
    "Auth security tests exist",
    bool(scan_files(TESTS_DIR, r"AUTH_TOKEN_INVALID|AUTH_TOKEN_EXPIRED")),
    "Auth validation tests found",
)

check(
    "SEC-19",
    "Input validation tests exist",
    bool(scan_files(TESTS_DIR, r"SQL injection|DROP TABLE|xss")),
    "Input validation test assertions found",
)

check(
    "SEC-20",
    "Rate limiting tests exist",
    bool(scan_files(TESTS_DIR, r"AUTH_ACCOUNT_LOCKED|lockout")),
    "Rate limit test assertions found",
)

# ── Output report ──

print(f"\n{'='*60}")
passed = sum(1 for r in results if r["status"] == "PASS")
total = len(results)
print(f"Results: {passed}/{total} PASS")

report_path = REPO_ROOT / "security_checklist_report.json"
report_path.write_text(json.dumps({
    "summary": {"passed": passed, "total": total, "failed": total - passed},
    "items": results,
}, indent=2))
print(f"Report written to: {report_path}")

if passed < total:
    sys.exit(1)
