#!/usr/bin/env python3
"""GET /health end-to-end latency benchmark (P50/P95, 100 iterations)."""

import json
import time

import numpy as np
import requests

ITERATIONS = 100
HEALTH_URL = "http://localhost:8420/health"


def run() -> dict:
    latencies: list[float] = []

    # Warm-up
    try:
        requests.get(HEALTH_URL, timeout=5)
    except requests.ConnectionError:
        return {
            "benchmark": "health",
            "error": "API not reachable at " + HEALTH_URL,
            "metrics": {},
        }

    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        resp = requests.get(HEALTH_URL, timeout=5)
        latencies.append((time.perf_counter() - t0) * 1000)
        assert resp.status_code == 200, f"Health check returned {resp.status_code}"

    lat = np.array(latencies)

    result = {
        "benchmark": "health",
        "iterations": ITERATIONS,
        "metrics": {
            "p50_ms": round(float(np.percentile(lat, 50)), 3),
            "p95_ms": round(float(np.percentile(lat, 95)), 3),
            "p99_ms": round(float(np.percentile(lat, 99)), 3),
        },
    }

    print(f"Health endpoint ({ITERATIONS} iterations):")
    print(f"  P50: {result['metrics']['p50_ms']}ms  P95: {result['metrics']['p95_ms']}ms  P99: {result['metrics']['p99_ms']}ms")

    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
