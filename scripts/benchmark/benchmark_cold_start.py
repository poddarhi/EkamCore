#!/usr/bin/env python3
"""Docker Compose cold start benchmark: down → up → all healthy (3 runs, mean)."""

import json
import subprocess
import time

RUNS = 3
COMPOSE_DIR = "."
TIMEOUT_SECONDS = 180


def _run_cmd(cmd: list[str], cwd: str = COMPOSE_DIR) -> int:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode


def _wait_healthy(timeout: float) -> float:
    """Wait until all containers are healthy. Returns elapsed seconds."""
    start = time.perf_counter()
    deadline = start + timeout

    while time.perf_counter() < deadline:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            cwd=COMPOSE_DIR,
        )
        if result.returncode != 0:
            time.sleep(2)
            continue

        lines = result.stdout.strip().split("\n")
        if not lines or lines == [""]:
            time.sleep(2)
            continue

        all_healthy = True
        has_services = False
        for line in lines:
            try:
                svc = json.loads(line)
            except json.JSONDecodeError:
                continue
            has_services = True
            health = svc.get("Health", "")
            state = svc.get("State", "")
            # migrate exits after completion
            if svc.get("Service", "") == "ekamcore-migrate":
                if state == "exited":
                    continue
            if health and health != "healthy":
                all_healthy = False
                break

        if has_services and all_healthy:
            return time.perf_counter() - start

        time.sleep(2)

    raise TimeoutError(f"Services not healthy within {timeout}s")


def run() -> dict:
    times: list[float] = []

    for i in range(RUNS):
        print(f"  Cold start run {i + 1}/{RUNS}...")

        # Down
        _run_cmd(["docker", "compose", "down"])
        time.sleep(2)

        # Up
        _run_cmd(["docker", "compose", "up", "-d"])

        try:
            elapsed = _wait_healthy(TIMEOUT_SECONDS)
            times.append(elapsed)
            print(f"    Healthy in {elapsed:.1f}s")
        except TimeoutError as e:
            print(f"    TIMEOUT: {e}")
            times.append(TIMEOUT_SECONDS)

    if not times:
        return {"benchmark": "cold_start", "error": "No runs completed", "metrics": {}}

    mean_s = sum(times) / len(times)

    result = {
        "benchmark": "cold_start",
        "runs": RUNS,
        "metrics": {
            "mean_seconds": round(mean_s, 1),
            "min_seconds": round(min(times), 1),
            "max_seconds": round(max(times), 1),
            "individual_seconds": [round(t, 1) for t in times],
        },
    }

    print(f"Cold start ({RUNS} runs):")
    print(f"  Mean: {result['metrics']['mean_seconds']}s  Min: {result['metrics']['min_seconds']}s  Max: {result['metrics']['max_seconds']}s")

    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
