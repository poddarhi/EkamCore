#!/usr/bin/env python3
"""Redis SET + GET latency benchmark (P50/P95/P99, 10000 iterations)."""

import json
import time

import numpy as np
import redis

ITERATIONS = 10000
REDIS_URL = "redis://:ekamcore_redis_dev@localhost:6379/3"


def run() -> dict:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()

    set_times: list[float] = []
    get_times: list[float] = []

    for i in range(ITERATIONS):
        key = f"bench:{i}"

        # SET
        t0 = time.perf_counter()
        r.set(key, f"value-{i}")
        set_times.append((time.perf_counter() - t0) * 1000)

        # GET
        t0 = time.perf_counter()
        r.get(key)
        get_times.append((time.perf_counter() - t0) * 1000)

    # Cleanup
    pipe = r.pipeline()
    for i in range(ITERATIONS):
        pipe.delete(f"bench:{i}")
    pipe.execute()
    r.close()

    s = np.array(set_times)
    g = np.array(get_times)

    result = {
        "benchmark": "redis",
        "iterations": ITERATIONS,
        "metrics": {
            "set_p50_ms": round(float(np.percentile(s, 50)), 3),
            "set_p95_ms": round(float(np.percentile(s, 95)), 3),
            "set_p99_ms": round(float(np.percentile(s, 99)), 3),
            "get_p50_ms": round(float(np.percentile(g, 50)), 3),
            "get_p95_ms": round(float(np.percentile(g, 95)), 3),
            "get_p99_ms": round(float(np.percentile(g, 99)), 3),
        },
    }

    print(f"Redis ({ITERATIONS} iterations):")
    print(f"  SET — P50: {result['metrics']['set_p50_ms']}ms  P95: {result['metrics']['set_p95_ms']}ms  P99: {result['metrics']['set_p99_ms']}ms")
    print(f"  GET — P50: {result['metrics']['get_p50_ms']}ms  P95: {result['metrics']['get_p95_ms']}ms  P99: {result['metrics']['get_p99_ms']}ms")

    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
