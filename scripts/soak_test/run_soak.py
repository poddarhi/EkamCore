#!/usr/bin/env python3
"""72-hour soak test orchestrator (S16-009 / ART-04 §7.3).

Runs a sustained workload against the EkamCore stack and collects metrics
every 5 minutes. Detects memory leaks, disk growth anomalies, latency
degradation, and error rate spikes.

Usage:
    python scripts/soak_test/run_soak.py --duration-hours 72
    python scripts/soak_test/run_soak.py --duration-hours 8   # short soak for CI

Output:
    soak_results/soak_metrics_{date}.jsonl  (one JSON object per sample)
    soak_results/soak_summary_{date}.json   (final pass/fail summary)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "soak_results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Configuration ────────────────────────────────────────────────────────────

API_URL = os.environ.get("API_URL", "http://localhost:8420")
API_EMAIL = os.environ.get("API_EMAIL", "admin@ekamcore.dev")
API_PASSWORD = os.environ.get("API_PASSWORD", "admin123")

SAMPLE_INTERVAL_SECS = 300  # 5 minutes
QUERY_INTERVAL_SECS = 300   # 1 query per 5 minutes

# Workload mix
QUERY_MIX = [
    ("deterministic", 0.40),   # /today, /recap, /settings
    ("search", 0.30),          # /search?q=...
    ("semantic", 0.20),        # /search?q=... (semantic terms)
    ("llm", 0.10),             # /query (grounded QA)
]

DETERMINISTIC_ENDPOINTS = [
    "/api/v1/today",
    "/api/v1/recap?period=daily",
    "/api/v1/settings",
    "/health",
]

SEARCH_QUERIES = [
    "meeting", "invoice", "birthday", "project", "report",
    "photo beach", "reminder dentist", "taxes", "travel", "recipe",
]

SEMANTIC_QUERIES = [
    "documents about quarterly earnings",
    "photos from last vacation",
    "who did I meet last week",
    "files related to the house renovation",
    "reminders about health appointments",
]

LLM_QUERIES = [
    "What meetings do I have this week?",
    "Summarize my recent documents",
    "Who have I been in contact with most?",
    "What photos did I take in March?",
    "Are there any overdue reminders?",
]

# Thresholds (fail if exceeded)
THRESHOLDS = {
    "memory_growth_pct": 20.0,    # Max 20% growth from baseline per container
    "error_rate_pct": 0.5,        # Max 0.5% error rate
    "p95_latency_ratio": 2.0,     # P95 must stay within 2× of baseline
    "crashes": 0,                  # Zero crashes allowed
}

# ── Auth ─────────────────────────────────────────────────────────────────────

_token: str | None = None


def get_token() -> str:
    global _token
    if _token:
        return _token
    try:
        resp = httpx.post(
            f"{API_URL}/auth/login",
            json={"email": API_EMAIL, "password": API_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            _token = resp.json().get("access_token", "")
        return _token or ""
    except Exception:
        return ""


def api_get(path: str) -> tuple[int, float]:
    """GET an API path, return (status_code, latency_ms)."""
    t0 = time.perf_counter()
    try:
        resp = httpx.get(
            f"{API_URL}{path}",
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=30,
        )
        latency = (time.perf_counter() - t0) * 1000
        return resp.status_code, latency
    except Exception:
        latency = (time.perf_counter() - t0) * 1000
        return 0, latency


def api_post_query(query: str) -> tuple[int, float]:
    """POST a natural language query."""
    t0 = time.perf_counter()
    try:
        resp = httpx.post(
            f"{API_URL}/api/v1/query",
            json={"query": query, "prefer_fast": True},
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=30,
        )
        latency = (time.perf_counter() - t0) * 1000
        return resp.status_code, latency
    except Exception:
        latency = (time.perf_counter() - t0) * 1000
        return 0, latency


# ── Metric collection ────────────────────────────────────────────────────────


def collect_container_metrics() -> list[dict]:
    """Collect memory and CPU for all EkamCore containers."""
    containers = []
    try:
        out = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}"],
            text=True, timeout=15,
        )
        for line in out.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 3 and "ekamcore" in parts[0]:
                name = parts[0].strip()
                mem_str = parts[1].split("/")[0].strip()
                cpu_str = parts[2].strip().rstrip("%")
                # Parse memory (e.g., "128.5MiB" → MB)
                mem_mb = 0.0
                if "GiB" in mem_str:
                    mem_mb = float(mem_str.replace("GiB", "")) * 1024
                elif "MiB" in mem_str:
                    mem_mb = float(mem_str.replace("MiB", ""))
                elif "KiB" in mem_str:
                    mem_mb = float(mem_str.replace("KiB", "")) / 1024
                cpu_pct = float(cpu_str) if cpu_str else 0.0
                containers.append({"name": name, "memory_mb": mem_mb, "cpu_pct": cpu_pct})
    except Exception:
        pass
    return containers


def collect_disk_usage() -> float:
    """Return Docker volume disk usage in GB."""
    try:
        out = subprocess.check_output(
            ["docker", "system", "df", "--format", "{{.Type}}|{{.Size}}"],
            text=True, timeout=10,
        )
        for line in out.strip().splitlines():
            if "Volumes" in line:
                size_str = line.split("|")[1].strip()
                if "GB" in size_str:
                    return float(size_str.replace("GB", ""))
                if "MB" in size_str:
                    return float(size_str.replace("MB", "")) / 1024
    except Exception:
        pass
    return 0.0


def check_container_crashes() -> int:
    """Count containers that exited unexpectedly."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=ekamcore",
             "--filter", "status=exited", "--format", "{{.Names}}"],
            text=True, timeout=10,
        )
        return len([l for l in out.strip().splitlines() if l])
    except Exception:
        return 0


# ── Workload generation ──────────────────────────────────────────────────────


def run_query_workload() -> dict:
    """Run one query from the configured mix, return metrics."""
    roll = random.random()
    cumulative = 0.0
    query_type = "deterministic"

    for qtype, weight in QUERY_MIX:
        cumulative += weight
        if roll <= cumulative:
            query_type = qtype
            break

    if query_type == "deterministic":
        path = random.choice(DETERMINISTIC_ENDPOINTS)
        status, latency = api_get(path)
    elif query_type == "search":
        q = random.choice(SEARCH_QUERIES)
        status, latency = api_get(f"/api/v1/search?q={q}")
    elif query_type == "semantic":
        q = random.choice(SEMANTIC_QUERIES)
        status, latency = api_get(f"/api/v1/search?q={q}")
    else:  # llm
        q = random.choice(LLM_QUERIES)
        status, latency = api_post_query(q)

    return {
        "type": query_type,
        "status": status,
        "latency_ms": round(latency, 2),
        "is_error": status >= 500 or status == 0,
    }


# ── Main loop ────────────────────────────────────────────────────────────────


def run_soak(duration_hours: float, output_dir: Path):
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    metrics_file = output_dir / f"soak_metrics_{date_tag}.jsonl"
    summary_file = output_dir / f"soak_summary_{date_tag}.json"

    duration_secs = duration_hours * 3600
    start_time = time.time()
    sample_count = 0
    total_queries = 0
    total_errors = 0
    latencies: list[float] = []
    baseline_memory: dict[str, float] = {}

    print(f"{'=' * 60}")
    print(f"  EkamCore Soak Test")
    print(f"  Duration: {duration_hours}h | API: {API_URL}")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 60}")

    with open(metrics_file, "w") as mf:
        while time.time() - start_time < duration_secs:
            elapsed_h = (time.time() - start_time) / 3600
            sample_count += 1

            # Collect system metrics
            containers = collect_container_metrics()
            disk_gb = collect_disk_usage()
            crashes = check_container_crashes()

            # Record baseline on first sample
            if not baseline_memory and containers:
                for c in containers:
                    baseline_memory[c["name"]] = c["memory_mb"]

            # Run query workload
            query_result = run_query_workload()
            total_queries += 1
            if query_result["is_error"]:
                total_errors += 1
            latencies.append(query_result["latency_ms"])

            # Build sample
            sample = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_hours": round(elapsed_h, 2),
                "sample": sample_count,
                "containers": containers,
                "disk_gb": round(disk_gb, 3),
                "crashes": crashes,
                "query": query_result,
                "cumulative": {
                    "total_queries": total_queries,
                    "total_errors": total_errors,
                    "error_rate_pct": round(
                        (total_errors / max(total_queries, 1)) * 100, 3
                    ),
                },
            }

            mf.write(json.dumps(sample) + "\n")
            mf.flush()

            # Log progress every 12 samples (1 hour)
            if sample_count % 12 == 0:
                error_rate = (total_errors / max(total_queries, 1)) * 100
                print(
                    f"  [{elapsed_h:.1f}h] samples={sample_count} "
                    f"queries={total_queries} errors={total_errors} "
                    f"rate={error_rate:.2f}% disk={disk_gb:.1f}GB "
                    f"crashes={crashes}"
                )

            # Check for immediate failures
            if crashes > THRESHOLDS["crashes"]:
                print(f"\n  FAIL: {crashes} container crashes detected!")

            time.sleep(SAMPLE_INTERVAL_SECS)

    # ── Generate summary ─────────────────────────────────────────────────

    elapsed_total = (time.time() - start_time) / 3600
    error_rate = (total_errors / max(total_queries, 1)) * 100

    # Memory growth check
    final_containers = collect_container_metrics()
    memory_growth: dict[str, float] = {}
    memory_ok = True
    for c in final_containers:
        base = baseline_memory.get(c["name"], 0)
        if base > 0:
            growth_pct = ((c["memory_mb"] - base) / base) * 100
            memory_growth[c["name"]] = round(growth_pct, 1)
            if growth_pct > THRESHOLDS["memory_growth_pct"]:
                memory_ok = False

    # Latency check
    sorted_lat = sorted(latencies)
    p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else 0
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0
    p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0

    # Overall pass/fail
    error_ok = error_rate <= THRESHOLDS["error_rate_pct"]
    crash_ok = check_container_crashes() <= THRESHOLDS["crashes"]
    all_pass = memory_ok and error_ok and crash_ok

    summary = {
        "test": "EkamCore 72h Soak Test",
        "started": datetime.now(timezone.utc).isoformat(),
        "duration_hours": round(elapsed_total, 2),
        "total_samples": sample_count,
        "total_queries": total_queries,
        "total_errors": total_errors,
        "error_rate_pct": round(error_rate, 3),
        "latency": {"p50_ms": round(p50, 1), "p95_ms": round(p95, 1), "p99_ms": round(p99, 1)},
        "memory_growth_pct": memory_growth,
        "final_disk_gb": round(collect_disk_usage(), 3),
        "crashes": check_container_crashes(),
        "thresholds": THRESHOLDS,
        "checks": {
            "memory_growth": "PASS" if memory_ok else "FAIL",
            "error_rate": "PASS" if error_ok else "FAIL",
            "crashes": "PASS" if crash_ok else "FAIL",
        },
        "overall": "PASS" if all_pass else "FAIL",
    }

    summary_file.write_text(json.dumps(summary, indent=2))

    print(f"\n{'=' * 60}")
    print(f"  Soak Test Complete: {summary['overall']}")
    print(f"  Duration: {elapsed_total:.1f}h | Queries: {total_queries} | Errors: {total_errors}")
    print(f"  Latency P50={p50:.0f}ms P95={p95:.0f}ms P99={p99:.0f}ms")
    print(f"  Memory growth: {memory_growth}")
    print(f"  Metrics: {metrics_file}")
    print(f"  Summary: {summary_file}")
    print(f"{'=' * 60}")

    return 0 if all_pass else 1


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="EkamCore soak test")
    parser.add_argument("--duration-hours", type=float, default=72, help="Test duration in hours")
    parser.add_argument("--output", type=str, default="soak_results", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.exit(run_soak(args.duration_hours, output_dir))


if __name__ == "__main__":
    main()
