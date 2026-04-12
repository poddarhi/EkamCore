#!/usr/bin/env python3
"""Test traceability coverage report generator (G-08 / ART-18).

Reads docs/test_traceability.json, verifies test functions exist via
pytest --collect-only, and generates an HTML report.

Usage:
    python scripts/test_coverage_report.py [--verify] [--output PATH]

Options:
    --verify   Run pytest --collect-only to check that listed test functions exist
    --output   Output path for HTML report (default: docs/test_coverage_report.html)
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACEABILITY_PATH = PROJECT_ROOT / "docs" / "test_traceability.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "test_coverage_report.html"

# ── Data loading ──────────────────────────────────────────────────────────────


def load_traceability() -> dict:
    if not TRACEABILITY_PATH.exists():
        print(f"ERROR: {TRACEABILITY_PATH} not found")
        sys.exit(1)
    return json.loads(TRACEABILITY_PATH.read_text())


def collect_pytest_tests() -> set[str]:
    """Run pytest --collect-only and return set of discovered test function names."""
    try:
        # Collect tests from api/tests and project-level tests/acceptance
        all_tests: set[str] = set()
        test_dirs = [
            (PROJECT_ROOT / "apps" / "api", "tests/"),
            (PROJECT_ROOT / "apps" / "api", "../../tests/acceptance/"),
        ]
        for cwd, test_path in test_dirs:
            # Use poetry run to ensure correct virtualenv
            result = subprocess.run(
                [
                    "poetry", "run", "pytest",
                    "--collect-only", "-q",
                    test_path,
                ],
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=60,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if "::" in line and not line.startswith("="):
                    parts = line.split("::")
                    func_name = parts[-1] if parts else ""
                    if func_name:
                        all_tests.add(func_name)
                    # Also add class::method format for matching
                    if len(parts) >= 3:
                        all_tests.add(f"{parts[-2]}::{parts[-1]}")
        return all_tests
    except Exception as e:
        print(f"WARNING: Could not collect pytest tests: {e}")
        return set()


# ── Verification ──────────────────────────────────────────────────────────────


def verify_test_functions(data: dict, discovered: set[str]) -> list[dict]:
    """Check which test functions from the traceability map actually exist."""
    issues = []
    for story_id, story in data["stories"].items():
        for func in story.get("test_functions", []):
            # Try exact match, Class::method match, and bare function name
            bare_name = func.split("::")[-1] if "::" in func else func
            found = (
                func in discovered
                or bare_name in discovered
            )
            if not found:
                issues.append({
                    "story_id": story_id,
                    "function": func,
                    "status": "NOT_FOUND",
                })
    return issues


# ── HTML generation ───────────────────────────────────────────────────────────


PHASE_NAMES = {
    0: "Phase 0 — Foundation",
    1: "Phase 1 — Core Features",
    2: "Phase 2 — File & Search",
    3: "Phase 3 — Face & People",
    4: "Phase 4 — Polish & Release",
}

STATUS_COLORS = {
    "full": "#22c55e",
    "partial": "#f59e0b",
    "none": "#ef4444",
}

STATUS_LABELS = {
    "full": "Full",
    "partial": "Partial",
    "none": "None",
}


def generate_html(data: dict, verification_issues: list[dict] | None, output_path: Path) -> None:
    summary = data["summary"]
    stories = data["stories"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Group stories by phase
    phases: dict[int, list[tuple[str, dict]]] = {}
    for sid, story in sorted(stories.items()):
        phase = story.get("phase", 99)
        phases.setdefault(phase, []).append((sid, story))

    # Calculate implemented coverage (Phase 0+1+2 only)
    implemented_stories = [s for s in stories.values() if s.get("phase", 99) <= 2]
    impl_covered = sum(1 for s in implemented_stories if s["coverage_status"] in ("full", "partial"))
    impl_total = len(implemented_stories)
    impl_pct = round(impl_covered / impl_total * 100, 1) if impl_total else 0

    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>EkamCore Test Coverage Report</title>",
        "<style>",
        "  * { margin: 0; padding: 0; box-sizing: border-box; }",
        "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #1e293b; padding: 2rem; max-width: 1200px; margin: 0 auto; }",
        "  h1 { font-size: 1.75rem; margin-bottom: 0.5rem; }",
        "  h2 { font-size: 1.25rem; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid #e2e8f0; }",
        "  h3 { font-size: 1rem; margin: 1.5rem 0 0.5rem; }",
        "  .meta { color: #64748b; font-size: 0.875rem; margin-bottom: 2rem; }",
        "  .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }",
        "  .card { background: white; border-radius: 0.75rem; padding: 1.25rem; border: 1px solid #e2e8f0; }",
        "  .card .label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }",
        "  .card .value { font-size: 2rem; font-weight: 700; margin-top: 0.25rem; }",
        "  .card .value.green { color: #22c55e; }",
        "  .card .value.amber { color: #f59e0b; }",
        "  .card .value.red { color: #ef4444; }",
        "  .bar { height: 8px; border-radius: 4px; background: #e2e8f0; overflow: hidden; margin-top: 0.5rem; }",
        "  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }",
        "  table { width: 100%; border-collapse: collapse; background: white; border-radius: 0.75rem; overflow: hidden; border: 1px solid #e2e8f0; margin-bottom: 1rem; }",
        "  th { background: #f1f5f9; text-align: left; padding: 0.75rem 1rem; font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }",
        "  td { padding: 0.75rem 1rem; border-top: 1px solid #f1f5f9; font-size: 0.875rem; vertical-align: top; }",
        "  tr:hover td { background: #f8fafc; }",
        "  .badge { display: inline-block; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }",
        "  .badge-full { background: #dcfce7; color: #166534; }",
        "  .badge-partial { background: #fef3c7; color: #92400e; }",
        "  .badge-none { background: #fee2e2; color: #991b1b; }",
        "  .badge-cp { background: #dbeafe; color: #1e40af; font-size: 0.625rem; margin-left: 0.25rem; }",
        "  .test-list { font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }",
        "  .phase-bar { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; }",
        "  .phase-label { font-size: 0.875rem; min-width: 200px; }",
        "  .phase-pct { font-size: 0.875rem; font-weight: 600; min-width: 50px; text-align: right; }",
        "  .phase-bar-track { flex: 1; height: 20px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }",
        "  .phase-bar-fill { height: 100%; border-radius: 4px; }",
        "  .issues { background: #fef2f2; border: 1px solid #fecaca; border-radius: 0.75rem; padding: 1rem; margin-top: 1rem; }",
        "  .issues h3 { color: #991b1b; }",
        "  .issues li { font-size: 0.875rem; margin: 0.25rem 0; }",
        "  .notes { font-size: 0.75rem; color: #94a3b8; font-style: italic; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>EkamCore Test Coverage Report</h1>",
        f'<p class="meta">Generated: {now} | Source: docs/test_traceability.json (ART-18)</p>',
        "",
        "<!-- Summary Cards -->",
        '<div class="summary-grid">',
        f'  <div class="card"><div class="label">Total Stories</div><div class="value">{summary["total_stories"]}</div></div>',
        f'  <div class="card"><div class="label">Fully Covered</div><div class="value green">{summary["fully_covered"]}</div></div>',
        f'  <div class="card"><div class="label">Partially Covered</div><div class="value amber">{summary["partially_covered"]}</div></div>',
        f'  <div class="card"><div class="label">Uncovered</div><div class="value red">{summary["uncovered"]}</div></div>',
        f'  <div class="card"><div class="label">Test Functions</div><div class="value">{summary["total_test_functions"]}</div></div>',
        f'  <div class="card"><div class="label">Implemented Coverage (P0-P2)</div><div class="value {"green" if impl_pct >= 80 else "amber" if impl_pct >= 60 else "red"}">{impl_pct}%</div></div>',
        "</div>",
        "",
        "<!-- Phase Coverage Bars -->",
        "<h2>Coverage by Phase</h2>",
    ]

    phase_data = summary.get("coverage_by_phase", {})
    for phase_key in ["phase_0", "phase_1", "phase_2", "phase_3", "phase_4"]:
        pd = phase_data.get(phase_key, {})
        pct = pd.get("coverage_pct", 0)
        total = pd.get("total", 0)
        covered = pd.get("covered", 0) + pd.get("partial", 0)
        phase_num = int(phase_key.split("_")[1])
        color = "#22c55e" if pct >= 80 else "#f59e0b" if pct >= 50 else "#ef4444"
        lines.append(f'<div class="phase-bar">')
        lines.append(f'  <span class="phase-label">{PHASE_NAMES.get(phase_num, phase_key)}</span>')
        lines.append(f'  <div class="phase-bar-track"><div class="phase-bar-fill" style="width:{pct}%;background:{color}"></div></div>')
        lines.append(f'  <span class="phase-pct" style="color:{color}">{pct}%</span>')
        lines.append(f'  <span class="notes">({covered}/{total})</span>')
        lines.append(f'</div>')

    # Sprint coverage
    lines.append("<h2>Coverage by Sprint</h2>")
    lines.append("<table><thead><tr><th>Sprint</th><th>Stories</th><th>Covered</th><th>Coverage</th><th>Bar</th></tr></thead><tbody>")
    sprint_data = summary.get("coverage_by_sprint", {})
    for sprint_key in sorted(sprint_data.keys(), key=lambda k: (0 if k.startswith("sprint_G") else 1, k)):
        sd = sprint_data[sprint_key]
        total = sd["total"]
        covered = sd["covered"]
        pct = sd["coverage_pct"]
        color = "#22c55e" if pct >= 80 else "#f59e0b" if pct >= 50 else "#ef4444"
        label = sprint_key.replace("sprint_", "Sprint ").replace("G", "Gap (G-*)")
        lines.append(f'<tr><td>{label}</td><td>{total}</td><td>{covered}</td><td style="color:{color};font-weight:600">{pct}%</td>')
        lines.append(f'<td><div class="bar" style="width:200px"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div></td></tr>')
    lines.append("</tbody></table>")

    # Story details per phase
    for phase_num in sorted(phases.keys()):
        phase_stories = phases[phase_num]
        lines.append(f"<h2>{PHASE_NAMES.get(phase_num, f'Phase {phase_num}')}</h2>")
        lines.append("<table><thead><tr><th>Story</th><th>Title</th><th>Status</th><th>Test Files</th><th>Tests</th></tr></thead><tbody>")

        for sid, story in phase_stories:
            status = story["coverage_status"]
            badge_class = f"badge-{status}"
            test_files = story.get("test_files", [])
            test_funcs = story.get("test_functions", [])
            cp = ' <span class="badge badge-cp">CP</span>' if story.get("critical_path") else ""
            notes = story.get("coverage_notes", "")

            files_html = "<br>".join(html.escape(f) for f in test_files) if test_files else '<span class="notes">—</span>'
            notes_html = f'<br><span class="notes">{html.escape(notes)}</span>' if notes else ""

            lines.append(f'<tr>')
            lines.append(f'  <td><strong>{html.escape(sid)}</strong>{cp}</td>')
            lines.append(f'  <td>{html.escape(story["title"])}{notes_html}</td>')
            lines.append(f'  <td><span class="badge {badge_class}">{STATUS_LABELS[status]}</span></td>')
            lines.append(f'  <td>{files_html}</td>')
            lines.append(f'  <td>{len(test_funcs)}</td>')
            lines.append(f'</tr>')

        lines.append("</tbody></table>")

    # Verification issues
    if verification_issues:
        lines.append('<div class="issues">')
        lines.append("<h3>Verification Issues</h3>")
        lines.append(f"<p>{len(verification_issues)} test function(s) listed in traceability but not found by pytest:</p>")
        lines.append("<ul>")
        for issue in verification_issues:
            lines.append(f'  <li><strong>{html.escape(issue["story_id"])}</strong>: {html.escape(issue["function"])}</li>')
        lines.append("</ul>")
        lines.append("</div>")

    # Uncovered stories list
    uncovered = [(sid, s) for sid, s in sorted(stories.items()) if s["coverage_status"] == "none"]
    if uncovered:
        lines.append("<h2>Uncovered Stories</h2>")
        lines.append("<table><thead><tr><th>Story</th><th>Title</th><th>Phase</th><th>Notes</th></tr></thead><tbody>")
        for sid, story in uncovered:
            notes = story.get("coverage_notes", "")
            lines.append(f'<tr><td>{html.escape(sid)}</td><td>{html.escape(story["title"])}</td><td>{story.get("phase", "?")}</td><td class="notes">{html.escape(notes)}</td></tr>')
        lines.append("</tbody></table>")

    lines.extend(["</body>", "</html>"])

    output_path.write_text("\n".join(lines))
    print(f"Report written to: {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="EkamCore test coverage report (G-08)")
    parser.add_argument("--verify", action="store_true", help="Verify test functions exist via pytest --collect-only")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output HTML path")
    args = parser.parse_args()

    data = load_traceability()
    print(f"Loaded traceability: {data['summary']['total_stories']} stories, {data['summary']['total_test_functions']} test functions")

    verification_issues = None
    if args.verify:
        print("Collecting pytest tests...")
        discovered = collect_pytest_tests()
        print(f"  Discovered {len(discovered)} test functions")
        verification_issues = verify_test_functions(data, discovered)
        if verification_issues:
            print(f"  WARNING: {len(verification_issues)} functions not found")
            for issue in verification_issues[:10]:
                print(f"    {issue['story_id']}: {issue['function']}")
        else:
            print("  All listed test functions verified")

    output_path = Path(args.output)
    generate_html(data, verification_issues, output_path)

    # Print summary
    s = data["summary"]
    total_implemented = s["fully_covered"] + s["partially_covered"]
    pct = round(total_implemented / s["total_stories"] * 100, 1) if s["total_stories"] else 0
    print(f"\nSummary: {s['fully_covered']} full + {s['partially_covered']} partial + {s['uncovered']} uncovered = {s['total_stories']} total ({pct}% covered)")

    # Phase 0+1 coverage for gate review
    phase_data = s.get("coverage_by_phase", {})
    for pk in ["phase_0", "phase_1"]:
        pd = phase_data.get(pk, {})
        print(f"  {pk}: {pd.get('coverage_pct', 0)}% ({pd.get('covered', 0) + pd.get('partial', 0)}/{pd.get('total', 0)})")


if __name__ == "__main__":
    main()
