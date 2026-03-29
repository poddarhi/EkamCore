#!/usr/bin/env python3
"""PostgreSQL INSERT + SELECT latency benchmark (P50/P95/P99, 1000 iterations)."""

import json
import time

import numpy as np
import psycopg2

ITERATIONS = 1000
DSN = "host=localhost port=5432 dbname=ekamcore user=ekamcore password=ekamcore_dev_password"


def run() -> dict:
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    # Setup temp table
    cur.execute("CREATE TEMP TABLE _bench (id SERIAL PRIMARY KEY, payload TEXT)")

    insert_times: list[float] = []
    select_times: list[float] = []

    for i in range(ITERATIONS):
        # INSERT
        t0 = time.perf_counter()
        cur.execute("INSERT INTO _bench (payload) VALUES (%s) RETURNING id", (f"row-{i}",))
        row_id = cur.fetchone()[0]
        insert_times.append((time.perf_counter() - t0) * 1000)

        # SELECT
        t0 = time.perf_counter()
        cur.execute("SELECT payload FROM _bench WHERE id = %s", (row_id,))
        cur.fetchone()
        select_times.append((time.perf_counter() - t0) * 1000)

    cur.close()
    conn.close()

    ins = np.array(insert_times)
    sel = np.array(select_times)

    result = {
        "benchmark": "postgres",
        "iterations": ITERATIONS,
        "metrics": {
            "insert_p50_ms": round(float(np.percentile(ins, 50)), 3),
            "insert_p95_ms": round(float(np.percentile(ins, 95)), 3),
            "insert_p99_ms": round(float(np.percentile(ins, 99)), 3),
            "select_p50_ms": round(float(np.percentile(sel, 50)), 3),
            "select_p95_ms": round(float(np.percentile(sel, 95)), 3),
            "select_p99_ms": round(float(np.percentile(sel, 99)), 3),
        },
    }

    print(f"PostgreSQL ({ITERATIONS} iterations):")
    print(f"  INSERT — P50: {result['metrics']['insert_p50_ms']}ms  P95: {result['metrics']['insert_p95_ms']}ms  P99: {result['metrics']['insert_p99_ms']}ms")
    print(f"  SELECT — P50: {result['metrics']['select_p50_ms']}ms  P95: {result['metrics']['select_p95_ms']}ms  P99: {result['metrics']['select_p99_ms']}ms")

    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
