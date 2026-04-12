#!/usr/bin/env python3
"""ML evaluation harness for LLM prompt quality (G-13 / ART-25).

Runs grounded QA and query classification test cases against Ollama,
computes quality metrics, and reports PASS/FAIL per ART-25 target.

Usage:
    python scripts/eval/run_eval.py [--model MODEL] [--ollama-url URL] [--cases-dir DIR]

Output:
    eval_results/{date}_{commit}.json   — per-case details + aggregate metrics
    eval_results/summary.md             — markdown table with PASS/FAIL per target
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ── Project paths ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "eval_results"
DEFAULT_CASES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "prompt_eval"

# Add api package to path so we can reuse prompt templates and output parser
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from api.services.query.prompts.grounded_qa_v1 import build_messages  # noqa: E402
from api.services.query.prompts.query_classify_v1 import build_classify_messages  # noqa: E402
from api.services.query.output_parser import parse_output  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────

SMALL_MODEL = "phi3:mini"
LARGE_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

METRIC_TARGETS = {
    "groundedness": 95.0,
    "source_accuracy": 98.0,
    "parse_success_rate": 95.0,
    "classification_accuracy": 90.0,
    "latency_p50_small_ms": 2000.0,
    "latency_p50_large_ms": 4000.0,
}


# ── Statistics ────────────────────────────────────────────────────────────────


def percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile (0–100) of a sorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


def pearson_correlation(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient between two lists."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


# ── Git metadata ──────────────────────────────────────────────────────────────


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


# ── Ollama calls ──────────────────────────────────────────────────────────────


def call_ollama(
    messages: list[dict[str, str]],
    model: str,
    ollama_url: str,
    temperature: float = 0.1,
    timeout_s: float = 15.0,
) -> tuple[str, float]:
    """Call Ollama /api/chat synchronously.

    Returns:
        Tuple of (response_content, latency_ms).
    """
    url = f"{ollama_url.rstrip('/')}/api/chat"
    start = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(5.0, read=timeout_s)) as client:
        resp = client.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
        resp.raise_for_status()
    elapsed_ms = (time.perf_counter() - start) * 1000
    data = resp.json()
    content: str = (data.get("message") or {}).get("content", "")
    return content, elapsed_ms


# ── Evaluation logic ──────────────────────────────────────────────────────────


def format_context(chunks: list[dict]) -> tuple[str, list[str]]:
    """Format context chunks into the text block expected by build_messages.

    Returns:
        Tuple of (context_text, list_of_filenames).
    """
    parts: list[str] = []
    filenames: list[str] = []
    for chunk in chunks:
        fn = chunk["filename"]
        filenames.append(fn)
        parts.append(f"[Document: {fn}]\n{chunk['text']}")
    return "\n\n".join(parts), filenames


def eval_qa_case(case: dict, model: str, ollama_url: str) -> dict:
    """Evaluate a single grounded QA case.

    Returns a result dict with scores and details.
    """
    context_text, valid_sources = format_context(case["context_chunks"])
    messages = build_messages(context_text, case["query"])

    result: dict = {
        "id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "model": model,
    }

    try:
        raw_output, latency_ms = call_ollama(
            messages, model, ollama_url, temperature=0.1, timeout_s=15.0
        )
        result["latency_ms"] = round(latency_ms, 2)
        result["raw_output"] = raw_output
    except Exception as e:
        result["error"] = str(e)
        result["parse_success"] = False
        result["grounded"] = False
        result["source_accurate"] = False
        return result

    # Parse output using production parser
    parsed = parse_output(raw_output, valid_sources)

    if parsed is None:
        result["parse_success"] = False
        result["grounded"] = False
        result["source_accurate"] = False
        return result

    result["parse_success"] = True
    result["answer"] = parsed.answer
    result["sources_used"] = parsed.sources_used
    result["confidence"] = parsed.confidence
    result["needs_more_context"] = parsed.needs_more_context

    # Groundedness: all expected keywords present in answer (case-insensitive)
    answer_lower = parsed.answer.lower()
    expected_keywords = case.get("expected_answer_contains", [])
    keywords_found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    result["grounded"] = len(keywords_found) == len(expected_keywords)
    result["keywords_found"] = keywords_found
    result["keywords_missing"] = [kw for kw in expected_keywords if kw.lower() not in answer_lower]

    # Source accuracy: no hallucinated sources (all cited sources in expected set)
    expected_source_set = set(case.get("expected_sources", []))
    cited_sources = set(parsed.sources_used)
    # Sources accurate if all cited sources are in expected set
    # (the output parser already filters against valid_sources from context)
    hallucinated = cited_sources - expected_source_set
    result["source_accurate"] = len(hallucinated) == 0
    result["hallucinated_sources"] = list(hallucinated)

    # Confidence correctness (for calibration)
    confidence_map = {"high": 3, "medium": 2, "low": 1}
    result["confidence_score"] = confidence_map.get(parsed.confidence, 1)
    result["is_correct"] = result["grounded"] and result["source_accurate"]

    return result


def eval_classify_case(case: dict, model: str, ollama_url: str) -> dict:
    """Evaluate a single query classification case."""
    messages = build_classify_messages(case["query"])

    result: dict = {
        "id": case["id"],
        "query": case["query"],
        "expected_category": case["expected_category"],
        "model": model,
    }

    try:
        raw_output, latency_ms = call_ollama(
            messages, model, ollama_url, temperature=0.0, timeout_s=5.0
        )
        result["latency_ms"] = round(latency_ms, 2)
        result["raw_output"] = raw_output
    except Exception as e:
        result["error"] = str(e)
        result["parse_success"] = False
        result["correct"] = False
        return result

    # Parse JSON output
    import re

    text = raw_output.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    try:
        data = json.loads(text)
        result["parse_success"] = True
        result["predicted_category"] = data.get("category", "")
        result["reasoning"] = data.get("reasoning", "")
        result["correct"] = (
            result["predicted_category"].lower() == case["expected_category"].lower()
        )
    except (json.JSONDecodeError, ValueError):
        result["parse_success"] = False
        result["correct"] = False

    return result


# ── Metrics computation ───────────────────────────────────────────────────────


def compute_metrics(
    qa_results: list[dict], classify_results: list[dict]
) -> dict:
    """Compute all 6 ART-25 metrics from eval results."""

    # --- QA metrics ---
    qa_with_output = [r for r in qa_results if "error" not in r]

    # Groundedness
    grounded_cases = [r for r in qa_with_output if r.get("grounded", False)]
    groundedness = (len(grounded_cases) / len(qa_with_output) * 100) if qa_with_output else 0.0

    # Source accuracy
    source_accurate_cases = [r for r in qa_with_output if r.get("source_accurate", False)]
    source_accuracy = (len(source_accurate_cases) / len(qa_with_output) * 100) if qa_with_output else 0.0

    # Parse success rate (across both QA and classify)
    all_results = qa_results + classify_results
    parsed_ok = [r for r in all_results if r.get("parse_success", False)]
    parse_success_rate = (len(parsed_ok) / len(all_results) * 100) if all_results else 0.0

    # Classification accuracy
    classify_correct = [r for r in classify_results if r.get("correct", False)]
    classification_accuracy = (
        len(classify_correct) / len(classify_results) * 100
    ) if classify_results else 0.0

    # Confidence calibration (Pearson correlation)
    conf_scores = [r["confidence_score"] for r in qa_with_output if "confidence_score" in r]
    correctness = [1.0 if r.get("is_correct", False) else 0.0 for r in qa_with_output if "confidence_score" in r]
    confidence_calibration = pearson_correlation(conf_scores, correctness)

    # Latency P50/P95 per model
    small_latencies = [r["latency_ms"] for r in all_results if r.get("model") == SMALL_MODEL and "latency_ms" in r]
    large_latencies = [r["latency_ms"] for r in all_results if r.get("model") == LARGE_MODEL and "latency_ms" in r]

    # Also collect all QA latencies grouped by model used
    qa_latencies = [r["latency_ms"] for r in qa_results if "latency_ms" in r]

    return {
        "groundedness": round(groundedness, 2),
        "source_accuracy": round(source_accuracy, 2),
        "parse_success_rate": round(parse_success_rate, 2),
        "classification_accuracy": round(classification_accuracy, 2),
        "confidence_calibration": round(confidence_calibration, 4),
        "latency": {
            "small_model": {
                "p50": round(percentile(small_latencies, 50), 2) if small_latencies else None,
                "p95": round(percentile(small_latencies, 95), 2) if small_latencies else None,
                "count": len(small_latencies),
            },
            "large_model": {
                "p50": round(percentile(large_latencies, 50), 2) if large_latencies else None,
                "p95": round(percentile(large_latencies, 95), 2) if large_latencies else None,
                "count": len(large_latencies),
            },
            "all_qa": {
                "p50": round(percentile(qa_latencies, 50), 2) if qa_latencies else None,
                "p95": round(percentile(qa_latencies, 95), 2) if qa_latencies else None,
                "count": len(qa_latencies),
            },
        },
        "counts": {
            "qa_total": len(qa_results),
            "qa_errors": len(qa_results) - len(qa_with_output),
            "classify_total": len(classify_results),
        },
    }


# ── Summary generation ────────────────────────────────────────────────────────


def check_target(value: float | None, target: float, comparison: str = ">=") -> str:
    if value is None:
        return "N/A"
    if comparison == ">=":
        return "PASS" if value >= target else "FAIL"
    elif comparison == "<":
        return "PASS" if value < target else "FAIL"
    return "N/A"


def generate_summary(metrics: dict, commit: str, timestamp: str) -> str:
    """Generate a markdown summary table."""
    lines = [
        f"# ML Evaluation Summary",
        f"",
        f"**Commit:** {commit}  ",
        f"**Date:** {timestamp}  ",
        f"**QA Cases:** {metrics['counts']['qa_total']} "
        f"({metrics['counts']['qa_errors']} errors)  ",
        f"**Classify Cases:** {metrics['counts']['classify_total']}",
        f"",
        f"## Metric Targets (ART-25)",
        f"",
        f"| Metric | Value | Target | Status |",
        f"|--------|-------|--------|--------|",
    ]

    rows = [
        (
            "Groundedness",
            f"{metrics['groundedness']:.1f}%",
            ">= 95%",
            check_target(metrics["groundedness"], 95.0),
        ),
        (
            "Source Accuracy",
            f"{metrics['source_accuracy']:.1f}%",
            ">= 98%",
            check_target(metrics["source_accuracy"], 98.0),
        ),
        (
            "Parse Success Rate",
            f"{metrics['parse_success_rate']:.1f}%",
            ">= 95%",
            check_target(metrics["parse_success_rate"], 95.0),
        ),
        (
            "Classification Accuracy",
            f"{metrics['classification_accuracy']:.1f}%",
            ">= 90%",
            check_target(metrics["classification_accuracy"], 90.0),
        ),
        (
            "Confidence Calibration",
            f"{metrics['confidence_calibration']:.4f}",
            "informational",
            "---",
        ),
    ]

    small_p50 = metrics["latency"]["small_model"]["p50"]
    large_p50 = metrics["latency"]["large_model"]["p50"]

    rows.append((
        "Latency P50 (small)",
        f"{small_p50:.0f}ms" if small_p50 is not None else "N/A",
        "< 2000ms",
        check_target(small_p50, 2000.0, "<") if small_p50 is not None else "N/A",
    ))
    rows.append((
        "Latency P50 (large)",
        f"{large_p50:.0f}ms" if large_p50 is not None else "N/A",
        "< 4000ms",
        check_target(large_p50, 4000.0, "<") if large_p50 is not None else "N/A",
    ))

    for metric, value, target, status in rows:
        icon = "PASS" if status == "PASS" else ("FAIL" if status == "FAIL" else status)
        lines.append(f"| {metric} | {value} | {target} | {icon} |")

    # Category breakdown
    lines.extend([
        "",
        "## Latency Details",
        "",
        "| Model | P50 (ms) | P95 (ms) | Count |",
        "|-------|----------|----------|-------|",
    ])

    for label, key in [("Small (phi3:mini)", "small_model"), ("Large (llama3.1:8b)", "large_model"), ("All QA", "all_qa")]:
        lat = metrics["latency"][key]
        p50 = f"{lat['p50']:.0f}" if lat["p50"] is not None else "N/A"
        p95 = f"{lat['p95']:.0f}" if lat["p95"] is not None else "N/A"
        lines.append(f"| {label} | {p50} | {p95} | {lat['count']} |")

    lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="EkamCore ML evaluation harness (G-13 / ART-25)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Override QA model (default: {SMALL_MODEL} for QA, {SMALL_MODEL} for classify)",
    )
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument(
        "--cases-dir",
        default=str(DEFAULT_CASES_DIR),
        help=f"Directory containing test case JSON files (default: {DEFAULT_CASES_DIR})",
    )
    args = parser.parse_args()

    cases_dir = Path(args.cases_dir)
    qa_model = args.model or SMALL_MODEL
    classify_model = args.model or SMALL_MODEL
    ollama_url = args.ollama_url

    commit = get_commit_hash()
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d_%H%M%S")

    print("=" * 60)
    print("  EkamCore ML Evaluation Harness (ART-25)")
    print(f"  Commit: {commit}")
    print(f"  QA Model: {qa_model} | Classify Model: {classify_model}")
    print(f"  Ollama: {ollama_url}")
    print("=" * 60)

    # Load test cases
    qa_path = cases_dir / "grounded_qa_cases.json"
    classify_path = cases_dir / "query_classify_cases.json"

    if not qa_path.exists():
        print(f"\n  ERROR: QA cases not found at {qa_path}")
        sys.exit(1)
    if not classify_path.exists():
        print(f"\n  ERROR: Classify cases not found at {classify_path}")
        sys.exit(1)

    qa_cases = json.loads(qa_path.read_text())["cases"]
    classify_cases = json.loads(classify_path.read_text())["cases"]

    print(f"\n  Loaded {len(qa_cases)} QA cases, {len(classify_cases)} classify cases")

    # Run QA evaluation
    print(f"\n  [Grounded QA — {qa_model}]")
    qa_results: list[dict] = []
    for i, case in enumerate(qa_cases, 1):
        print(f"    [{i}/{len(qa_cases)}] {case['id']}: {case['query'][:50]}...", end=" ", flush=True)
        result = eval_qa_case(case, qa_model, ollama_url)
        qa_results.append(result)

        if "error" in result:
            print(f"ERROR: {result['error'][:60]}")
        elif not result["parse_success"]:
            print("PARSE_FAIL")
        else:
            g = "G" if result["grounded"] else "g"
            s = "S" if result["source_accurate"] else "s"
            print(f"[{g}{s}] {result.get('latency_ms', 0):.0f}ms conf={result.get('confidence', '?')}")

    # Run classification evaluation
    print(f"\n  [Query Classification — {classify_model}]")
    classify_results: list[dict] = []
    for i, case in enumerate(classify_cases, 1):
        print(f"    [{i}/{len(classify_cases)}] {case['id']}: {case['query'][:50]}...", end=" ", flush=True)
        result = eval_classify_case(case, classify_model, ollama_url)
        classify_results.append(result)

        if "error" in result:
            print(f"ERROR: {result['error'][:60]}")
        elif not result["parse_success"]:
            print("PARSE_FAIL")
        else:
            icon = "correct" if result["correct"] else "WRONG"
            predicted = result.get("predicted_category", "?")
            print(f"[{icon}] predicted={predicted} expected={case['expected_category']} {result.get('latency_ms', 0):.0f}ms")

    # Compute metrics
    metrics = compute_metrics(qa_results, classify_results)

    # Build output
    output = {
        "timestamp": now.isoformat(),
        "commit": commit,
        "models": {"qa": qa_model, "classify": classify_model},
        "ollama_url": ollama_url,
        "metrics": metrics,
        "qa_results": qa_results,
        "classify_results": classify_results,
    }

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{date_str}_{commit}.json"
    result_path.write_text(json.dumps(output, indent=2))
    print(f"\n  Results saved to: {result_path}")

    # Generate and save summary
    summary = generate_summary(metrics, commit, now.strftime("%Y-%m-%d %H:%M:%S UTC"))
    summary_path = RESULTS_DIR / "summary.md"
    summary_path.write_text(summary)
    print(f"  Summary saved to: {summary_path}")

    # Print summary to console
    print(f"\n{'=' * 60}")
    print(summary)
    print("=" * 60)

    # Determine exit code
    failures = []
    if metrics["groundedness"] < METRIC_TARGETS["groundedness"]:
        failures.append(f"Groundedness {metrics['groundedness']:.1f}% < {METRIC_TARGETS['groundedness']}%")
    if metrics["source_accuracy"] < METRIC_TARGETS["source_accuracy"]:
        failures.append(f"Source Accuracy {metrics['source_accuracy']:.1f}% < {METRIC_TARGETS['source_accuracy']}%")
    if metrics["parse_success_rate"] < METRIC_TARGETS["parse_success_rate"]:
        failures.append(f"Parse Success {metrics['parse_success_rate']:.1f}% < {METRIC_TARGETS['parse_success_rate']}%")
    if metrics["classification_accuracy"] < METRIC_TARGETS["classification_accuracy"]:
        failures.append(f"Classification {metrics['classification_accuracy']:.1f}% < {METRIC_TARGETS['classification_accuracy']}%")

    small_p50 = metrics["latency"]["small_model"]["p50"]
    if small_p50 is not None and small_p50 >= METRIC_TARGETS["latency_p50_small_ms"]:
        failures.append(f"Small P50 {small_p50:.0f}ms >= {METRIC_TARGETS['latency_p50_small_ms']:.0f}ms")

    large_p50 = metrics["latency"]["large_model"]["p50"]
    if large_p50 is not None and large_p50 >= METRIC_TARGETS["latency_p50_large_ms"]:
        failures.append(f"Large P50 {large_p50:.0f}ms >= {METRIC_TARGETS['latency_p50_large_ms']:.0f}ms")

    if failures:
        print("\n  FAILED targets:")
        for f in failures:
            print(f"    x {f}")
        sys.exit(1)
    else:
        print("\n  All ART-25 targets PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
