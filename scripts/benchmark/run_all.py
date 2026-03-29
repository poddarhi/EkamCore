#!/usr/bin/env python3
"""Run all EkamCore performance benchmarks and save baseline.json."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is importable
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
os.chdir(PROJECT_ROOT)

BASELINE_PATH = PROJECT_ROOT / "benchmarks" / "baseline.json"


def main() -> None:
    print("=" * 60)
    print("  EkamCore Performance Benchmark Suite")
    print("=" * 60)
    print()

    results: list[dict] = []
    errors: list[str] = []

    # Import and run each benchmark
    benchmarks = [
        ("PostgreSQL", "benchmark_postgres"),
        ("Redis", "benchmark_redis"),
        ("Qdrant", "benchmark_qdrant"),
        ("Health Endpoint", "benchmark_health"),
        ("Cold Start", "benchmark_cold_start"),
    ]

    for label, module_name in benchmarks:
        print(f"--- {label} ---")
        try:
            # Dynamic import from same directory
            mod = __import__(module_name)
            result = mod.run()
            results.append(result)
        except Exception as e:
            error_msg = f"{label}: {type(e).__name__}: {e}"
            print(f"  ERROR: {error_msg}")
            errors.append(error_msg)
            results.append({
                "benchmark": module_name.replace("benchmark_", ""),
                "error": str(e),
                "metrics": {},
            })
        print()

    # Build baseline document
    baseline = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmarks": results,
    }

    if errors:
        baseline["errors"] = errors

    # Save
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n")
    print(f"Baseline saved to {BASELINE_PATH.relative_to(PROJECT_ROOT)}")

    # Summary table
    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    for r in results:
        name = r.get("benchmark", "unknown")
        if r.get("error"):
            print(f"  {name:20s}  ERROR: {r['error']}")
            continue
        metrics = r.get("metrics", {})
        parts = [f"{k}: {v}" for k, v in metrics.items() if not k.startswith("individual")]
        print(f"  {name:20s}  {', '.join(parts)}")
    print()

    if errors:
        print(f"  {len(errors)} benchmark(s) had errors.")
        sys.exit(1)
    else:
        print("  All benchmarks completed successfully.")


if __name__ == "__main__":
    # Add script dir to path for sibling imports
    sys.path.insert(0, str(SCRIPT_DIR))
    main()
