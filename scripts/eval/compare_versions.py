#!/usr/bin/env python3
"""Compare two ML evaluation result files (G-13 / ART-25).

Shows metric changes between prompt version A and B to support A/B testing
of prompt template changes.

Usage:
    python scripts/eval/compare_versions.py <result_a.json> <result_b.json>

Output:
    Console table with metric deltas (green = improved, red = regressed)
    eval_results/comparison_{timestamp}.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "eval_results"

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def load_results(path: Path) -> dict:
    """Load and validate an eval results JSON file."""
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    data = json.loads(path.read_text())
    if "metrics" not in data:
        print(f"ERROR: No 'metrics' key in {path}")
        sys.exit(1)
    return data


def format_delta(delta: float, higher_is_better: bool, suffix: str = "") -> str:
    """Format a delta value with color and direction indicator."""
    if abs(delta) < 0.01:
        return f"  {delta:+.2f}{suffix}"
    if (delta > 0 and higher_is_better) or (delta < 0 and not higher_is_better):
        return f"{GREEN}{delta:+.2f}{suffix}{RESET}"
    else:
        return f"{RED}{delta:+.2f}{suffix}{RESET}"


def format_delta_md(delta: float, higher_is_better: bool, suffix: str = "") -> str:
    """Format a delta value for markdown (no ANSI codes)."""
    if abs(delta) < 0.01:
        return f"{delta:+.2f}{suffix}"
    if (delta > 0 and higher_is_better) or (delta < 0 and not higher_is_better):
        return f"{delta:+.2f}{suffix} (improved)"
    else:
        return f"{delta:+.2f}{suffix} (regressed)"


def compare(a: dict, b: dict) -> list[dict]:
    """Compare metrics between two eval results. Returns list of comparison rows."""
    ma = a["metrics"]
    mb = b["metrics"]

    rows = []

    # Percentage metrics (higher is better)
    for key, label in [
        ("groundedness", "Groundedness"),
        ("source_accuracy", "Source Accuracy"),
        ("parse_success_rate", "Parse Success Rate"),
        ("classification_accuracy", "Classification Accuracy"),
    ]:
        va = ma.get(key, 0.0)
        vb = mb.get(key, 0.0)
        rows.append({
            "metric": label,
            "value_a": f"{va:.1f}%",
            "value_b": f"{vb:.1f}%",
            "delta": vb - va,
            "higher_is_better": True,
            "suffix": "%",
        })

    # Confidence calibration (higher is better)
    ca = ma.get("confidence_calibration", 0.0)
    cb = mb.get("confidence_calibration", 0.0)
    rows.append({
        "metric": "Confidence Calibration",
        "value_a": f"{ca:.4f}",
        "value_b": f"{cb:.4f}",
        "delta": cb - ca,
        "higher_is_better": True,
        "suffix": "",
    })

    # Latency metrics (lower is better)
    for model_key, label in [
        ("small_model", "Latency P50 (small)"),
        ("large_model", "Latency P50 (large)"),
    ]:
        lat_a = ma.get("latency", {}).get(model_key, {})
        lat_b = mb.get("latency", {}).get(model_key, {})
        p50_a = lat_a.get("p50")
        p50_b = lat_b.get("p50")

        if p50_a is not None and p50_b is not None:
            rows.append({
                "metric": label,
                "value_a": f"{p50_a:.0f}ms",
                "value_b": f"{p50_b:.0f}ms",
                "delta": p50_b - p50_a,
                "higher_is_better": False,
                "suffix": "ms",
            })
        else:
            rows.append({
                "metric": label,
                "value_a": f"{p50_a:.0f}ms" if p50_a is not None else "N/A",
                "value_b": f"{p50_b:.0f}ms" if p50_b is not None else "N/A",
                "delta": 0.0,
                "higher_is_better": False,
                "suffix": "ms",
            })

    return rows


def print_table(a: dict, b: dict, rows: list[dict]) -> None:
    """Print a formatted comparison table to console."""
    commit_a = a.get("commit", "unknown")
    commit_b = b.get("commit", "unknown")
    ts_a = a.get("timestamp", "")[:19]
    ts_b = b.get("timestamp", "")[:19]

    print(f"\n{'=' * 76}")
    print(f"  ML Evaluation Comparison")
    print(f"  Version A: {commit_a} ({ts_a})")
    print(f"  Version B: {commit_b} ({ts_b})")
    print(f"{'=' * 76}")
    print(f"\n  {'Metric':<28} {'A':>10} {'B':>10} {'Delta':>18}")
    print(f"  {'-' * 28} {'-' * 10} {'-' * 10} {'-' * 18}")

    for row in rows:
        delta_str = format_delta(row["delta"], row["higher_is_better"], row["suffix"])
        print(f"  {row['metric']:<28} {row['value_a']:>10} {row['value_b']:>10} {delta_str:>18}")

    print(f"\n{'=' * 76}")

    # Summary
    improved = sum(1 for r in rows if (
        (r["delta"] > 0.01 and r["higher_is_better"]) or
        (r["delta"] < -0.01 and not r["higher_is_better"])
    ))
    regressed = sum(1 for r in rows if (
        (r["delta"] < -0.01 and r["higher_is_better"]) or
        (r["delta"] > 0.01 and not r["higher_is_better"])
    ))
    unchanged = len(rows) - improved - regressed

    print(f"  {GREEN}{improved} improved{RESET} | {RED}{regressed} regressed{RESET} | {unchanged} unchanged")
    print(f"{'=' * 76}\n")


def generate_comparison_md(a: dict, b: dict, rows: list[dict]) -> str:
    """Generate a markdown comparison report."""
    commit_a = a.get("commit", "unknown")
    commit_b = b.get("commit", "unknown")
    ts_a = a.get("timestamp", "")[:19]
    ts_b = b.get("timestamp", "")[:19]

    lines = [
        "# ML Evaluation Comparison",
        "",
        f"| | Version A | Version B |",
        f"|---|---|---|",
        f"| **Commit** | {commit_a} | {commit_b} |",
        f"| **Date** | {ts_a} | {ts_b} |",
        f"| **QA Model** | {a.get('models', {}).get('qa', '?')} | {b.get('models', {}).get('qa', '?')} |",
        f"| **Classify Model** | {a.get('models', {}).get('classify', '?')} | {b.get('models', {}).get('classify', '?')} |",
        "",
        "## Metrics",
        "",
        "| Metric | A | B | Delta |",
        "|--------|---|---|-------|",
    ]

    for row in rows:
        delta_str = format_delta_md(row["delta"], row["higher_is_better"], row["suffix"])
        lines.append(f"| {row['metric']} | {row['value_a']} | {row['value_b']} | {delta_str} |")

    lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/eval/compare_versions.py <result_a.json> <result_b.json>")
        sys.exit(1)

    path_a = Path(sys.argv[1])
    path_b = Path(sys.argv[2])

    a = load_results(path_a)
    b = load_results(path_b)

    rows = compare(a, b)

    # Print to console
    print_table(a, b, rows)

    # Save markdown
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    md_path = RESULTS_DIR / f"comparison_{ts}.md"
    md_path.write_text(generate_comparison_md(a, b, rows))
    print(f"  Comparison saved to: {md_path}")


if __name__ == "__main__":
    main()
