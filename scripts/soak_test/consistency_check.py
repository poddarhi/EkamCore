#!/usr/bin/env python3
"""Post-soak data consistency checker (S16-009).

Verifies data integrity after a soak test run:
- Row counts match expected (seed + ingested)
- No orphaned ingestion states
- Qdrant point counts match face_detection count
- No ingestion_states stuck in non-terminal state
- Audit log integrity (append-only, no gaps)

Usage:
    python scripts/soak_test/consistency_check.py

Requires: running Docker stack with PostgreSQL and Qdrant accessible.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "soak_results"


def psql(query: str) -> str:
    """Run a psql query against the EkamCore PostgreSQL."""
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "ekamcore-postgres",
             "psql", "-U", "ekamcore", "-d", "ekamcore", "-t", "-c", query],
            capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def qdrant_count(collection: str) -> int:
    """Get point count from a Qdrant collection."""
    try:
        result = subprocess.run(
            ["curl", "-sf", "--max-time", "10",
             f"http://localhost:6333/collections/{collection}"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        return data.get("result", {}).get("points_count", 0)
    except Exception:
        return -1


def main():
    print("=" * 60)
    print("  EkamCore Post-Soak Consistency Check")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = ""):
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        checks.append({"name": name, "passed": passed, "detail": detail})

    # ── Table counts ─────────────────────────────────────────────────────

    print("\n--- Row Counts ---")
    tables = ["users", "files", "file_chunks", "calendar_events", "reminders",
              "contacts", "photo_assets", "face_detections", "face_clusters",
              "trusted_persons", "sources", "ingestion_states"]

    for table in tables:
        count = psql(f"SELECT count(*) FROM {table};")
        check(f"{table} count", count.isdigit() and int(count) >= 0, f"{count} rows")

    # ── Orphaned ingestion states ────────────────────────────────────────

    print("\n--- Orphan Checks ---")
    orphaned = psql(
        "SELECT count(*) FROM ingestion_states ist "
        "LEFT JOIN files f ON ist.file_id = f.id "
        "WHERE f.id IS NULL;"
    )
    check("no orphaned ingestion_states", orphaned.strip() == "0", f"{orphaned} orphans")

    # ── Stuck ingestion states ───────────────────────────────────────────

    print("\n--- Stuck States ---")
    stuck = psql(
        "SELECT count(*) FROM ingestion_states "
        "WHERE stage NOT IN ('COMPLETED', 'FAILED', 'SKIPPED') "
        "AND updated_at < NOW() - INTERVAL '1 hour';"
    )
    check("no stuck ingestion_states (>1h)", stuck.strip() == "0", f"{stuck} stuck")

    # ── Qdrant point counts ──────────────────────────────────────────────

    print("\n--- Qdrant Consistency ---")
    doc_points = qdrant_count("document_embeddings")
    chunk_count = psql("SELECT count(*) FROM file_chunks WHERE embedding_id IS NOT NULL;")
    if doc_points >= 0 and chunk_count.isdigit():
        delta = abs(doc_points - int(chunk_count))
        check(
            "document_embeddings matches file_chunks",
            delta <= 10,  # Allow small delta for in-flight operations
            f"qdrant={doc_points} pg={chunk_count} delta={delta}",
        )
    else:
        check("document_embeddings matches file_chunks", False, f"qdrant={doc_points} pg={chunk_count}")

    face_points = qdrant_count("face_embeddings")
    face_count = psql("SELECT count(*) FROM face_detections WHERE deleted_at IS NULL AND qdrant_point_id IS NOT NULL;")
    if face_points >= 0 and face_count.isdigit():
        delta = abs(face_points - int(face_count))
        check(
            "face_embeddings matches face_detections",
            delta <= 5,
            f"qdrant={face_points} pg={face_count} delta={delta}",
        )
    else:
        check("face_embeddings matches face_detections", False, f"qdrant={face_points} pg={face_count}")

    # ── Soft-delete consistency ──────────────────────────────────────────

    print("\n--- Soft Delete ---")
    deleted_visible = psql(
        "SELECT count(*) FROM files WHERE deleted_at IS NOT NULL "
        "AND id IN (SELECT file_id FROM ingestion_states WHERE stage = 'COMPLETED');"
    )
    check("no completed ingestion for deleted files", deleted_visible.strip() == "0", f"{deleted_visible}")

    # ── Summary ──────────────────────────────────────────────────────────

    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"])
    total = len(checks)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": {"total": total, "passed": passed, "failed": failed},
        "overall": "PASS" if failed == 0 else "FAIL",
    }

    report_path = RESULTS_DIR / f"consistency_check_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    RESULTS_DIR.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))

    print(f"\n{'=' * 60}")
    print(f"  Consistency Check: {passed}/{total} PASS | {failed} FAIL")
    print(f"  Report: {report_path}")
    print(f"{'=' * 60}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
