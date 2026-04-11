"""API endpoint response time benchmarks (G-06 / ART-16).

Measures round-trip latency for key endpoints against the running stack.
Requires: ``make up`` (all services running via Docker).
"""

from __future__ import annotations

import time

import requests

BASE_URL = "https://localhost"
VERIFY_SSL = False  # Self-signed cert in dev

# Suppress InsecureRequestWarning for self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_session: requests.Session | None = None
_token: str | None = None


def _get_session() -> requests.Session:
    global _session, _token
    if _session is None:
        _session = requests.Session()
        _session.verify = VERIFY_SSL
        # Login to get a token
        resp = _session.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": "admin@ekamcore.dev", "password": "admin123"},
        )
        if resp.status_code == 200:
            _token = resp.json()["access_token"]
    return _session


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_token}"} if _token else {}


def _get_workspace_id() -> str:
    """Extract workspace_id from the JWT."""
    import base64, json as _json
    if not _token:
        return ""
    payload = _token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    claims = _json.loads(base64.urlsafe_b64decode(payload))
    workspaces = claims.get("workspaces", [])
    return workspaces[0] if workspaces else ""


def _bench_get(path: str) -> float:
    """Time a GET request, return elapsed in ms."""
    s = _get_session()
    start = time.perf_counter()
    resp = s.get(f"{BASE_URL}{path}", headers=_auth_headers())
    elapsed_ms = (time.perf_counter() - start) * 1000
    if resp.status_code >= 500:
        raise RuntimeError(f"GET {path} returned {resp.status_code}")
    return elapsed_ms


def _bench_post(path: str, body: dict) -> float:
    """Time a POST request, return elapsed in ms."""
    s = _get_session()
    start = time.perf_counter()
    resp = s.post(f"{BASE_URL}{path}", json=body, headers=_auth_headers())
    elapsed_ms = (time.perf_counter() - start) * 1000
    if resp.status_code >= 500:
        raise RuntimeError(f"POST {path} returned {resp.status_code}")
    return elapsed_ms


def get_benchmarks() -> list[dict]:
    ws = _get_workspace_id()

    return [
        {
            "name": "api/today",
            "target_p50_ms": 200,
            "target_p95_ms": 500,
            "fn": lambda: _bench_get(f"/api/v1/today?workspace_id={ws}"),
        },
        {
            "name": "api/search",
            "target_p50_ms": 300,
            "target_p95_ms": 800,
            "fn": lambda: _bench_get(f"/api/v1/search?q=test&workspace_id={ws}"),
        },
        {
            "name": "api/query_deterministic",
            "target_p50_ms": 500,
            "target_p95_ms": 2000,
            "fn": lambda: _bench_post(
                "/api/v1/query",
                {"query": "what meetings do I have today", "workspace_id": ws, "prefer_fast": True},
            ),
        },
        {
            "name": "api/health",
            "target_p50_ms": 100,
            "target_p95_ms": 300,
            "fn": lambda: _bench_get("/health"),
        },
        {
            "name": "api/settings",
            "target_p50_ms": 100,
            "target_p95_ms": 300,
            "fn": lambda: _bench_get("/api/v1/settings"),
        },
    ]
