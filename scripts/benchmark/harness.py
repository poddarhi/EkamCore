#!/usr/bin/env python3
"""Performance benchmark harness (G-06 / ART-16).

Runs each benchmark N times, computes percentiles, compares against the
baseline, and reports PASS/FAIL per target.

Usage:
    python scripts/benchmark/harness.py [--iterations N] [--save-baseline]

Output:
    benchmarks/results/{date}_{commit}.json
    Console table with PASS/FAIL per target
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "benchmarks" / "results"
BASELINE_PATH = PROJECT_ROOT / "benchmarks" / "baseline.json"
BENCHMARKS_DIR = Path(__file__).resolve().parent / "benchmarks"

sys.path.insert(0, str(BENCHMARKS_DIR))


# ── Statistics ──────────────────────────────────────────────────────────────


def percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile (0–100) of a sorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


def compute_stats(timings: list[float]) -> dict:
    """Compute P50, P95, P99, mean, stddev from a list of timings (ms)."""
    n = len(timings)
    if n == 0:
        return {"p50": 0, "p95": 0, "p99": 0, "mean": 0, "stddev": 0, "count": 0}

    mean = sum(timings) / n
    variance = sum((t - mean) ** 2 for t in timings) / n
    return {
        "p50": round(percentile(timings, 50), 2),
        "p95": round(percentile(timings, 95), 2),
        "p99": round(percentile(timings, 99), 2),
        "mean": round(mean, 2),
        "stddev": round(math.sqrt(variance), 2),
        "count": n,
    }


# ── Git metadata ────────────────────────────────────────────────────────────


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


# ── Benchmark discovery and execution ───────────────────────────────────────


def discover_benchmarks() -> list[tuple[str, object]]:
    """Import all benchmark modules from the benchmarks/ directory."""
    modules = []
    for f in sorted(BENCHMARKS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        name = f.stem
        spec = importlib.util.spec_from_file_location(name, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        modules.append((name, mod))
    return modules


def run_benchmark(mod, iterations: int) -> list[dict]:
    """Run a benchmark module's ``get_benchmarks()`` function.

    Each benchmark module must expose:
        get_benchmarks() -> list[BenchmarkDef]

    Where BenchmarkDef is:
        {"name": str, "target_p50_ms": float, "target_p95_ms": float, "fn": callable}

    The callable ``fn()`` runs one iteration and returns elapsed milliseconds.
    """
    if not hasattr(mod, "get_benchmarks"):
        return []

    results = []
    for bench in mod.get_benchmarks():
        name = bench["name"]
        target_p50 = bench.get("target_p50_ms")
        target_p95 = bench.get("target_p95_ms")
        fn = bench["fn"]

        print(f"    {name} ({iterations} iterations)...", end=" ", flush=True)

        timings = []
        for _ in range(iterations):
            try:
                elapsed = fn()
                if elapsed is not None:
                    timings.append(elapsed)
            except Exception as e:
                print(f"ERROR: {e}")
                break

        stats = compute_stats(timings)

        # Compare against targets
        p50_ok = target_p50 is None or stats["p50"] <= target_p50
        p95_ok = target_p95 is None or stats["p95"] <= target_p95

        status = "PASS" if (p50_ok and p95_ok) else "FAIL"
        icon = "✓" if status == "PASS" else "✗"
        print(f"[{icon}] P50={stats['p50']}ms P95={stats['p95']}ms")

        results.append({
            "name": name,
            "stats": stats,
            "target_p50_ms": target_p50,
            "target_p95_ms": target_p95,
            "status": status,
        })

    return results


# ── Baseline comparison ─────────────────────────────────────────────────────


def compare_with_baseline(results: list[dict]) -> list[dict]:
    """Compare results against baseline.json if it exists."""
    if not BASELINE_PATH.exists():
        return results

    baseline = json.loads(BASELINE_PATH.read_text())
    baseline_map = {r["name"]: r for r in baseline.get("benchmarks", [])}

    for r in results:
        base = baseline_map.get(r["name"])
        if base:
            base_p50 = base["stats"]["p50"]
            base_p95 = base["stats"]["p95"]
            if base_p50 > 0:
                r["p50_deviation_pct"] = round(
                    (r["stats"]["p50"] - base_p50) / base_p50 * 100, 1
                )
            if base_p95 > 0:
                r["p95_deviation_pct"] = round(
                    (r["stats"]["p95"] - base_p95) / base_p95 * 100, 1
                )
            # Flag regression if >20% worse
            if r.get("p95_deviation_pct", 0) > 20:
                r["regression_warning"] = True

    return results


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="EkamCore performance benchmark harness")
    parser.add_argument("--iterations", "-n", type=int, default=100, help="Iterations per benchmark")
    parser.add_argument("--save-baseline", action="store_true", help="Save results as new baseline")
    args = parser.parse_args()

    commit = get_commit_hash()
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d_%H%M%S")

    print("=" * 60)
    print("  EkamCore Performance Benchmark Harness")
    print(f"  Commit: {commit} | Iterations: {args.iterations}")
    print("=" * 60)

    all_results: list[dict] = []
    modules = discover_benchmarks()

    if not modules:
        print("\n  No benchmark modules found in scripts/benchmark/benchmarks/")
        sys.exit(1)

    for mod_name, mod in modules:
        print(f"\n  [{mod_name}]")
        results = run_benchmark(mod, args.iterations)
        all_results.extend(results)

    # Compare with baseline
    all_results = compare_with_baseline(all_results)

    # Build output
    output = {
        "timestamp": now.isoformat(),
        "commit": commit,
        "iterations": args.iterations,
        "benchmarks": all_results,
        "summary": {
            "total": len(all_results),
            "passed": sum(1 for r in all_results if r["status"] == "PASS"),
            "failed": sum(1 for r in all_results if r["status"] == "FAIL"),
            "regressions": sum(1 for r in all_results if r.get("regression_warning")),
        },
    }

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{date_str}_{commit}.json"
    result_path.write_text(json.dumps(output, indent=2))
    print(f"\n  Results saved to: {result_path}")

    # Optionally save as baseline
    if args.save_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(output, indent=2))
        print(f"  Baseline saved to: {BASELINE_PATH}")

    # Summary
    s = output["summary"]
    print(f"\n{'=' * 60}")
    print(f"  Results: {s['passed']}/{s['total']} PASS | {s['failed']} FAIL | {s['regressions']} regressions")
    print("=" * 60)

    if s["failed"] > 0:
        print("\n  FAILED benchmarks:")
        for r in all_results:
            if r["status"] == "FAIL":
                print(f"    ✗ {r['name']}: P50={r['stats']['p50']}ms (target: {r['target_p50_ms']}ms)"
                      f" P95={r['stats']['p95']}ms (target: {r['target_p95_ms']}ms)")

    if s["regressions"] > 0:
        print("\n  WARNING: Regressions detected (>20% worse than baseline):")
        for r in all_results:
            if r.get("regression_warning"):
                print(f"    ⚠ {r['name']}: P95 deviation {r.get('p95_deviation_pct', '?')}%")

    sys.exit(1 if s["failed"] > 0 else 0)


if __name__ == "__main__":
    main()
