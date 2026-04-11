"""Database query performance benchmarks (G-06 / ART-16).

Measures raw SQL query execution time via direct DB connection.
Requires: PostgreSQL running (via ``make up``).
"""

from __future__ import annotations

import os
import time

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://ekamcore:ekamcore_dev_password@localhost:5432/ekamcore",
)

_conn = None


def _get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL)
        _conn.autocommit = True
    return _conn


def _bench_query(sql: str, params: tuple = ()) -> float:
    """Time a SQL query, return elapsed in ms."""
    conn = _get_conn()
    cur = conn.cursor()
    start = time.perf_counter()
    cur.execute(sql, params)
    cur.fetchall()
    elapsed_ms = (time.perf_counter() - start) * 1000
    cur.close()
    return elapsed_ms


def get_benchmarks() -> list[dict]:
    return [
        {
            "name": "db/sources_list",
            "target_p50_ms": 50,
            "target_p95_ms": 100,
            "fn": lambda: _bench_query(
                "SELECT id, name, type, status FROM sources WHERE deleted_at IS NULL LIMIT 100"
            ),
        },
        {
            "name": "db/files_fulltext_search",
            "target_p50_ms": 100,
            "target_p95_ms": 200,
            "fn": lambda: _bench_query(
                "SELECT id, filename FROM files WHERE deleted_at IS NULL AND filename ILIKE %s LIMIT 20",
                ("%test%",),
            ),
        },
        {
            "name": "db/today_card_assembly",
            "target_p50_ms": 150,
            "target_p95_ms": 300,
            "fn": lambda: _bench_query(
                """
                SELECT 'event' AS type, id, created_at FROM calendar_events
                UNION ALL
                SELECT 'reminder' AS type, id, created_at FROM reminders WHERE deleted_at IS NULL
                LIMIT 50
                """
            ),
        },
        {
            "name": "db/photo_assets_by_location",
            "target_p50_ms": 50,
            "target_p95_ms": 100,
            "fn": lambda: _bench_query(
                "SELECT id, gps_lat, gps_lon, location_name FROM photo_assets "
                "WHERE deleted_at IS NULL AND location_name ILIKE %s LIMIT 20",
                ("%San%",),
            ),
        },
        {
            "name": "db/settings_lookup",
            "target_p50_ms": 20,
            "target_p95_ms": 50,
            "fn": lambda: _bench_query(
                "SELECT key, value_json FROM settings WHERE namespace = %s LIMIT 20",
                ("core",),
            ),
        },
    ]
