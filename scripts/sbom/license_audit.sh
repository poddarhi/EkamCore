#!/usr/bin/env bash
# EkamCore license audit (G-12 / ART-24)
#
# Checks all project dependencies against an allowed license list.
# Uses pip-licenses for Python and pnpm licenses for Node.
#
# Allowed: MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Python-2.0,
#          PSF-2.0, 0BSD, Unlicense, CC0-1.0, MPL-2.0
# Flagged (fail): GPL-2.0, GPL-3.0, AGPL-3.0, LGPL-2.1, LGPL-3.0, SSPL-1.0
# Unknown/NOASSERTION: warning (manual review needed)
#
# Usage:
#   ./scripts/sbom/license_audit.sh [--output-dir DIR]
#
# Output:
#   sbom/license_audit_report.json
#
# Exit codes:
#   0 — all licenses allowed
#   1 — GPL/AGPL/SSPL found (requires legal review)
#
# Must be run from the EkamCore project root.

set -uo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/sbom"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        *)            echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$OUTPUT_DIR"
REPORT_FILE="${OUTPUT_DIR}/license_audit_report.json"

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "============================================================"
log "  EkamCore License Audit (ART-24)"
log "============================================================"

# ── Audit Python dependencies ────────────────────────────────────────────────

log ""
log "[Python Dependencies]"

PYTHON_PACKAGES="[]"

# Try pip-licenses first (requires packages installed in venv)
if command -v pip-licenses &> /dev/null; then
    PYTHON_RAW=$(pip-licenses --format=json 2>/dev/null || echo "[]")
    PYTHON_PACKAGES="$PYTHON_RAW"
    PKG_COUNT=$(echo "$PYTHON_PACKAGES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    log "  pip-licenses: ${PKG_COUNT} packages"
elif [[ -f "${PROJECT_ROOT}/apps/api/poetry.lock" ]]; then
    # Fallback: try running pip-licenses via poetry
    PYTHON_RAW=$(cd "${PROJECT_ROOT}/apps/api" && poetry run pip-licenses --format=json 2>/dev/null || echo "[]")
    PYTHON_PACKAGES="$PYTHON_RAW"
    PKG_COUNT=$(echo "$PYTHON_PACKAGES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [[ "$PKG_COUNT" == "0" ]]; then
        log "  pip-licenses not available — extracting from poetry.lock metadata"
        # Parse poetry.lock for package names (licenses will be NOASSERTION)
        PYTHON_PACKAGES=$(python3 -c "
import re, json
from pathlib import Path
lock = Path('${PROJECT_ROOT}/apps/api/poetry.lock').read_text()
pkgs = []
for m in re.finditer(r'\[\[package\]\]\nname = \"(.+?)\"\nversion = \"(.+?)\"', lock):
    pkgs.append({'Name': m.group(1), 'Version': m.group(2), 'License': 'NOASSERTION'})
print(json.dumps(pkgs))
" 2>/dev/null || echo "[]")
        PKG_COUNT=$(echo "$PYTHON_PACKAGES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        log "  Parsed ${PKG_COUNT} packages from poetry.lock (licenses as NOASSERTION)"
    else
        log "  poetry run pip-licenses: ${PKG_COUNT} packages"
    fi
else
    log "  [warn] No Python dependency source found"
fi

# ── Audit Node dependencies ──────────────────────────────────────────────────

log ""
log "[Node Dependencies]"

NODE_PACKAGES="[]"

if [[ -f "${PROJECT_ROOT}/apps/web/package.json" ]]; then
    # Try pnpm licenses
    if command -v pnpm &> /dev/null; then
        NODE_RAW=$(cd "${PROJECT_ROOT}/apps/web" && pnpm licenses list --json 2>/dev/null || echo "")
        if [[ -n "$NODE_RAW" ]] && echo "$NODE_RAW" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
            NODE_PACKAGES=$(echo "$NODE_RAW" | python3 -c "
import sys, json
data = json.load(sys.stdin)
pkgs = []
# pnpm licenses list --json returns {license: [packages]}
if isinstance(data, dict):
    for license_id, packages in data.items():
        if isinstance(packages, list):
            for pkg in packages:
                name = pkg.get('name', pkg) if isinstance(pkg, dict) else str(pkg)
                version = pkg.get('version', '') if isinstance(pkg, dict) else ''
                pkgs.append({'Name': name, 'Version': version, 'License': license_id})
print(json.dumps(pkgs))
" 2>/dev/null || echo "[]")
            PKG_COUNT=$(echo "$NODE_PACKAGES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
            log "  pnpm licenses: ${PKG_COUNT} packages"
        else
            log "  [warn] pnpm licenses failed — parsing package.json"
        fi
    fi

    # Fallback: extract from package.json (no license info)
    if [[ "$NODE_PACKAGES" == "[]" ]]; then
        NODE_PACKAGES=$(python3 -c "
import json
from pathlib import Path
pkg = json.loads(Path('${PROJECT_ROOT}/apps/web/package.json').read_text())
pkgs = []
for dep_type in ['dependencies', 'devDependencies']:
    for name, version in pkg.get(dep_type, {}).items():
        pkgs.append({'Name': name, 'Version': version.lstrip('^~>=<'), 'License': 'NOASSERTION'})
print(json.dumps(pkgs))
" 2>/dev/null || echo "[]")
        PKG_COUNT=$(echo "$NODE_PACKAGES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        log "  Parsed ${PKG_COUNT} packages from package.json (licenses as NOASSERTION)"
    fi
else
    log "  [warn] No Node dependency source found"
fi

# ── Classify licenses ────────────────────────────────────────────────────────

log ""
log "[License Classification]"

python3 -c "
import json, sys, re
from datetime import datetime, timezone

ALLOWED = {
    'MIT', 'MIT License',
    'Apache-2.0', 'Apache 2.0', 'Apache Software License',
    'BSD-2-Clause', 'BSD 2-Clause', 'BSD License',
    'BSD-3-Clause', 'BSD 3-Clause',
    'ISC', 'ISC License',
    'Python-2.0', 'PSF-2.0', 'Python Software Foundation License',
    '0BSD',
    'Unlicense', 'The Unlicense',
    'CC0-1.0', 'CC-BY-4.0',
    'MPL-2.0', 'Mozilla Public License 2.0',
    'Artistic-2.0',
}

FLAGGED = {
    'GPL-2.0', 'GPL-2.0-only', 'GPL-2.0-or-later',
    'GPL-3.0', 'GPL-3.0-only', 'GPL-3.0-or-later',
    'GNU General Public License v2',
    'GNU General Public License v3',
    'AGPL-3.0', 'AGPL-3.0-only', 'AGPL-3.0-or-later',
    'GNU Affero General Public License v3',
    'LGPL-2.1', 'LGPL-2.1-only', 'LGPL-2.1-or-later',
    'LGPL-3.0', 'LGPL-3.0-only', 'LGPL-3.0-or-later',
    'GNU Lesser General Public License v2',
    'GNU Lesser General Public License v3',
    'SSPL-1.0',
}

def classify(license_str):
    if not license_str or license_str in ('NOASSERTION', 'UNKNOWN', 'Unknown'):
        return 'unknown'
    # Check each part of multi-license (e.g. 'MIT; BSD-3-Clause')
    parts = re.split(r'[;,\s]+(?:AND|OR|and|or)\s+|[;,]+\s*', license_str)
    for part in parts:
        part = part.strip()
        if any(f.lower() in part.lower() for f in FLAGGED):
            return 'flagged'
    for part in parts:
        part = part.strip()
        if any(a.lower() == part.lower() for a in ALLOWED):
            continue
        if any(a.lower() in part.lower() for a in ALLOWED):
            continue
        # Not in allowed list
        if any(f.lower() in part.lower() for f in FLAGGED):
            return 'flagged'
        return 'unknown'
    return 'allowed'

python_pkgs = json.loads('''${PYTHON_PACKAGES}''')
node_pkgs = json.loads('''${NODE_PACKAGES}''')

results = []
allowed_count = 0
flagged_count = 0
unknown_count = 0

for source, pkgs in [('python', python_pkgs), ('node', node_pkgs)]:
    for pkg in pkgs:
        name = pkg.get('Name', pkg.get('name', ''))
        version = pkg.get('Version', pkg.get('version', ''))
        license_id = pkg.get('License', pkg.get('license', 'NOASSERTION'))
        status = classify(license_id)

        results.append({
            'source': source,
            'package': name,
            'version': version,
            'license': license_id,
            'status': status,
        })

        if status == 'allowed':
            allowed_count += 1
        elif status == 'flagged':
            flagged_count += 1
        else:
            unknown_count += 1

report = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'summary': {
        'total_packages': len(results),
        'allowed': allowed_count,
        'flagged': flagged_count,
        'unknown': unknown_count,
        'python_packages': len(python_pkgs),
        'node_packages': len(node_pkgs),
    },
    'allowed_licenses': sorted(ALLOWED),
    'flagged_licenses': sorted(FLAGGED),
    'packages': results,
}

with open('${REPORT_FILE}', 'w') as f:
    json.dump(report, f, indent=2)

# Print summary
print(f'  Total: {len(results)} packages')
print(f'  Allowed: {allowed_count}')
print(f'  Flagged (GPL/AGPL/SSPL): {flagged_count}')
print(f'  Unknown (needs review): {unknown_count}')

if flagged_count > 0:
    print()
    print('  FLAGGED PACKAGES (require legal review):')
    for r in results:
        if r['status'] == 'flagged':
            print(f'    [{r[\"source\"]}] {r[\"package\"]} {r[\"version\"]}: {r[\"license\"]}')

if unknown_count > 0:
    print()
    print(f'  UNKNOWN LICENSES ({unknown_count} packages — manual check needed):')
    shown = 0
    for r in results:
        if r['status'] == 'unknown' and shown < 10:
            print(f'    [{r[\"source\"]}] {r[\"package\"]} {r[\"version\"]}: {r[\"license\"]}')
            shown += 1
    if unknown_count > 10:
        print(f'    ... and {unknown_count - 10} more')

# Exit with error if flagged
sys.exit(1 if flagged_count > 0 else 0)
"
AUDIT_EXIT=$?

log ""
log "============================================================"
log "  Report: ${REPORT_FILE}"
if [[ $AUDIT_EXIT -eq 0 ]]; then
    log "  Result: PASS (no GPL/AGPL/SSPL dependencies)"
else
    log "  Result: FAIL (flagged dependencies found — legal review required)"
fi
log "============================================================"

exit $AUDIT_EXIT
