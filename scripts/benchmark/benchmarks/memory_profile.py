"""Container memory usage benchmarks (G-06 / ART-16).

Reads Docker container stats and compares against the RAM budget
from docker-compose.yml memory limits.
"""

from __future__ import annotations

import json
import subprocess
import time


# Memory limits from docker-compose.yml (in MB)
MEMORY_LIMITS_MB: dict[str, int] = {
    "ekamcore-postgres": 768,
    "ekamcore-redis": 192,
    "ekamcore-qdrant": 1024,
    "ekamcore-paperless": 1024,
    "ekamcore-api": 768,
    "ekamcore-workers": 768,
    "ekamcore-web": 128,
    "ekamcore-proxy": 128,
}


def _get_container_memory_mb(container_name: str) -> float | None:
    """Get current memory usage of a Docker container in MB."""
    try:
        output = subprocess.check_output(
            ["docker", "stats", container_name, "--no-stream", "--format", "{{.MemUsage}}"],
            text=True,
            timeout=10,
        ).strip()
        # Parse "123.4MiB / 768MiB" or "1.2GiB / 1GiB"
        used_str = output.split("/")[0].strip()
        if "GiB" in used_str:
            return float(used_str.replace("GiB", "").strip()) * 1024
        elif "MiB" in used_str:
            return float(used_str.replace("MiB", "").strip())
        elif "KiB" in used_str:
            return float(used_str.replace("KiB", "").strip()) / 1024
        return None
    except Exception:
        return None


def _make_memory_bench(container: str, limit_mb: int):
    """Create a benchmark function for a container's memory usage."""
    def fn():
        mem = _get_container_memory_mb(container)
        if mem is None:
            return None  # Container not running — skip
        pct = (mem / limit_mb) * 100
        # Return the percentage as "elapsed_ms" (repurposed for memory %)
        return pct
    return fn


def get_benchmarks() -> list[dict]:
    benchmarks = []
    for container, limit in MEMORY_LIMITS_MB.items():
        # Target: under 80% of limit
        benchmarks.append({
            "name": f"memory/{container}",
            "target_p50_ms": 80,   # repurposed: max 80% of limit
            "target_p95_ms": 90,   # repurposed: max 90% of limit
            "fn": _make_memory_bench(container, limit),
        })
    return benchmarks
