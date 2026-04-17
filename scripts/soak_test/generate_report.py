#!/usr/bin/env python3
"""Generate markdown soak test report from metrics JSONL (S16-009).

Reads the soak_metrics JSONL file and produces a human-readable report
with memory trends, disk growth, latency percentiles, and pass/fail.

Usage:
    python scripts/soak_test/generate_report.py soak_results/soak_metrics_*.jsonl
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main():
    if len(sys.argv) < 2:
        # Find the latest metrics file
        results_dir = PROJECT_ROOT / "soak_results"
        jsonl_files = sorted(results_dir.glob("soak_metrics_*.jsonl"))
        if not jsonl_files:
            print("No soak metrics files found.")
            sys.exit(1)
        metrics_path = jsonl_files[-1]
    else:
        metrics_path = Path(sys.argv[1])

    if not metrics_path.exists():
        print(f"File not found: {metrics_path}")
        sys.exit(1)

    # Parse JSONL
    samples: list[dict] = []
    for line in metrics_path.read_text().splitlines():
        if line.strip():
            samples.append(json.loads(line))

    if not samples:
        print("No samples found in metrics file.")
        sys.exit(1)

    # Extract series
    hours = [s["elapsed_hours"] for s in samples]
    latencies = [s["query"]["latency_ms"] for s in samples]
    errors = [s["cumulative"]["total_errors"] for s in samples]
    disk = [s["disk_gb"] for s in samples]

    # Memory per container over time
    container_memory: dict[str, list[float]] = {}
    for s in samples:
        for c in s.get("containers", []):
            container_memory.setdefault(c["name"], []).append(c["memory_mb"])

    # Stats
    total_queries = samples[-1]["cumulative"]["total_queries"]
    total_errors_val = samples[-1]["cumulative"]["total_errors"]
    error_rate = samples[-1]["cumulative"]["error_rate_pct"]
    duration = samples[-1]["elapsed_hours"]

    sorted_lat = sorted(latencies)
    p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else 0
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0
    p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0

    # Memory growth
    memory_growth: dict[str, str] = {}
    for name, mem_series in container_memory.items():
        if len(mem_series) >= 2 and mem_series[0] > 0:
            growth = ((mem_series[-1] - mem_series[0]) / mem_series[0]) * 100
            memory_growth[name] = f"{growth:+.1f}%"

    # Find summary file
    summary_files = sorted((metrics_path.parent).glob("soak_summary_*.json"))
    overall = "UNKNOWN"
    if summary_files:
        summary = json.loads(summary_files[-1].read_text())
        overall = summary.get("overall", "UNKNOWN")

    # Generate report
    report = f"""# Soak Test Report (S16-009)

**Date:** {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
**Duration:** {duration:.1f} hours
**Metrics file:** {metrics_path.name}
**Overall:** **{overall}**

## Summary

| Metric | Value |
|--------|-------|
| Total samples | {len(samples)} |
| Total queries | {total_queries} |
| Total errors | {total_errors_val} |
| Error rate | {error_rate:.3f}% |
| Duration | {duration:.1f}h |

## Latency

| Percentile | Value |
|-----------|-------|
| P50 | {p50:.0f} ms |
| P95 | {p95:.0f} ms |
| P99 | {p99:.0f} ms |

## Memory Growth

| Container | Growth |
|-----------|--------|
"""
    for name, growth_str in sorted(memory_growth.items()):
        report += f"| {name} | {growth_str} |\n"

    report += f"""
## Disk Usage

| Metric | Value |
|--------|-------|
| Start | {disk[0]:.2f} GB |
| End | {disk[-1]:.2f} GB |
| Growth | {disk[-1] - disk[0]:.2f} GB |

## Threshold Checks

| Check | Threshold | Result |
|-------|-----------|--------|
| Memory growth | < 20% per container | {"PASS" if all(float(v.rstrip("%")) <= 20 for v in memory_growth.values()) else "FAIL" if memory_growth else "N/A"} |
| Error rate | < 0.5% | {"PASS" if error_rate <= 0.5 else "FAIL"} |
| Container crashes | 0 | {"PASS" if samples[-1].get("crashes", 0) == 0 else "FAIL"} |

## Notes

- Workload mix: 40% deterministic, 30% search, 20% semantic, 10% LLM
- Query interval: 5 minutes (1 query per sample)
- Hardware: {sys.platform} (document actual hardware for release gate)
"""

    report_path = PROJECT_ROOT / "docs" / "soak_test_report.md"
    report_path.write_text(report)
    print(f"Report generated: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
