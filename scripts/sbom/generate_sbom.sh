#!/usr/bin/env bash
# EkamCore SBOM generation (G-12 / ART-24)
#
# Generates Software Bill of Materials in SPDX JSON format for:
#   - Docker images: api, workers, web, migrate
#   - Python dependencies (from poetry.lock)
#   - Node dependencies (from pnpm-lock.yaml)
#
# Uses syft (https://github.com/anchore/syft) when available.
# Falls back to pip-licenses / pnpm licenses for local dev.
#
# Usage:
#   ./scripts/sbom/generate_sbom.sh [--output-dir DIR]
#
# Output:
#   sbom/{service}_sbom.json  — per Docker image SPDX
#   sbom/python_deps.json     — Python dependency SBOM
#   sbom/node_deps.json       — Node dependency SBOM
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

log() { echo "[$(date +%H:%M:%S)] $*"; }

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GENERATED=0
FAILED=0

log "============================================================"
log "  EkamCore SBOM Generation (ART-24)"
log "  Output: $OUTPUT_DIR"
log "============================================================"

# ── Check for syft ────────────────────────────────────────────────────────────

HAS_SYFT=false
if command -v syft &> /dev/null; then
    HAS_SYFT=true
    SYFT_VERSION=$(syft version 2>/dev/null | head -1 || echo "unknown")
    log "syft found: ${SYFT_VERSION}"
else
    log "syft not found — using fallback methods"
    log "Install syft: https://github.com/anchore/syft#installation"
fi

# ── Docker image SBOMs ───────────────────────────────────────────────────────

DOCKER_SERVICES=(
    "ekamcore-api"
    "ekamcore-workers"
    "ekamcore-web"
    "ekamcore-migrate"
)

log ""
log "[Docker Image SBOMs]"

for service in "${DOCKER_SERVICES[@]}"; do
    output_file="${OUTPUT_DIR}/${service}_sbom.json"

    if [[ "$HAS_SYFT" == "true" ]]; then
        # Check if image exists locally
        image_id=$(docker images -q "$service" 2>/dev/null | head -1)
        if [[ -z "$image_id" ]]; then
            # Try with docker compose project prefix
            image_id=$(docker images -q "*${service}*" 2>/dev/null | head -1)
        fi

        if [[ -n "$image_id" ]]; then
            if syft "docker:${service}" -o spdx-json > "$output_file" 2>/dev/null; then
                size=$(wc -c < "$output_file" | tr -d ' ')
                log "  [ok] ${service}: ${size} bytes (SPDX JSON)"
                ((GENERATED++))
            else
                log "  [warn] ${service}: syft scan failed — trying by image ID"
                if syft "docker:${image_id}" -o spdx-json > "$output_file" 2>/dev/null; then
                    log "  [ok] ${service}: generated via image ID"
                    ((GENERATED++))
                else
                    log "  [fail] ${service}: syft scan failed"
                    ((FAILED++))
                fi
            fi
        else
            log "  [skip] ${service}: image not built locally — build first with 'docker compose build'"
            # Generate a placeholder noting the image needs building
            python3 -c "
import json
doc = {
    'spdxVersion': 'SPDX-2.3',
    'dataLicense': 'CC0-1.0',
    'SPDXID': 'SPDXRef-DOCUMENT',
    'name': '${service}',
    'documentNamespace': 'https://ekamcore.dev/sbom/${service}',
    'creationInfo': {
        'created': '${TIMESTAMP}',
        'creators': ['Tool: ekamcore-sbom-generator'],
        'comment': 'Image not available locally. Build with docker compose build before generating SBOM.'
    },
    'packages': []
}
with open('${output_file}', 'w') as f:
    json.dump(doc, f, indent=2)
"
            log "  [placeholder] ${service}: placeholder SBOM created"
            ((GENERATED++))
        fi
    else
        # Fallback: create minimal SBOM from docker inspect
        log "  [skip] ${service}: syft not available"
        python3 -c "
import json
doc = {
    'spdxVersion': 'SPDX-2.3',
    'dataLicense': 'CC0-1.0',
    'SPDXID': 'SPDXRef-DOCUMENT',
    'name': '${service}',
    'documentNamespace': 'https://ekamcore.dev/sbom/${service}',
    'creationInfo': {
        'created': '${TIMESTAMP}',
        'creators': ['Tool: ekamcore-sbom-generator-fallback'],
        'comment': 'Install syft for full SBOM. This is a placeholder.'
    },
    'packages': []
}
with open('${output_file}', 'w') as f:
    json.dump(doc, f, indent=2)
"
        ((GENERATED++))
    fi
done

# ── Python dependency SBOM ───────────────────────────────────────────────────

log ""
log "[Python Dependencies]"

PYTHON_OUTPUT="${OUTPUT_DIR}/python_deps.json"

if [[ "$HAS_SYFT" == "true" ]] && [[ -f "${PROJECT_ROOT}/apps/api/poetry.lock" ]]; then
    if syft "dir:${PROJECT_ROOT}/apps/api" -o spdx-json > "$PYTHON_OUTPUT" 2>/dev/null; then
        size=$(wc -c < "$PYTHON_OUTPUT" | tr -d ' ')
        log "  [ok] python_deps: ${size} bytes (syft SPDX from poetry.lock)"
        ((GENERATED++))
    else
        log "  [warn] syft failed on api dir — trying fallback"
        HAS_SYFT_PYTHON=false
    fi
else
    HAS_SYFT_PYTHON=false
fi

if [[ "${HAS_SYFT_PYTHON:-true}" == "false" ]] || [[ "$HAS_SYFT" != "true" ]]; then
    # Fallback: parse poetry.lock directly
    if [[ -f "${PROJECT_ROOT}/apps/api/poetry.lock" ]]; then
        python3 -c "
import json, re
from pathlib import Path

lock_text = Path('${PROJECT_ROOT}/apps/api/poetry.lock').read_text()
packages = []
for match in re.finditer(r'\[\[package\]\]\nname = \"(.+?)\"\nversion = \"(.+?)\"', lock_text):
    name, version = match.groups()
    packages.append({
        'SPDXID': f'SPDXRef-Package-{name}-{version}',
        'name': name,
        'versionInfo': version,
        'downloadLocation': f'https://pypi.org/project/{name}/{version}/',
        'supplier': 'NOASSERTION',
        'licenseDeclared': 'NOASSERTION',
    })

doc = {
    'spdxVersion': 'SPDX-2.3',
    'dataLicense': 'CC0-1.0',
    'SPDXID': 'SPDXRef-DOCUMENT',
    'name': 'ekamcore-python-deps',
    'documentNamespace': 'https://ekamcore.dev/sbom/python-deps',
    'creationInfo': {
        'created': '${TIMESTAMP}',
        'creators': ['Tool: ekamcore-sbom-generator-fallback'],
        'comment': f'Parsed from poetry.lock. {len(packages)} packages found.'
    },
    'packages': packages
}
with open('${PYTHON_OUTPUT}', 'w') as f:
    json.dump(doc, f, indent=2)
print(f'  [ok] python_deps: {len(packages)} packages from poetry.lock (fallback)')
"
        ((GENERATED++))
    else
        log "  [fail] poetry.lock not found at apps/api/poetry.lock"
        ((FAILED++))
    fi
fi

# ── Node dependency SBOM ─────────────────────────────────────────────────────

log ""
log "[Node Dependencies]"

NODE_OUTPUT="${OUTPUT_DIR}/node_deps.json"

if [[ "$HAS_SYFT" == "true" ]] && [[ -f "${PROJECT_ROOT}/apps/web/pnpm-lock.yaml" ]]; then
    if syft "dir:${PROJECT_ROOT}/apps/web" -o spdx-json > "$NODE_OUTPUT" 2>/dev/null; then
        size=$(wc -c < "$NODE_OUTPUT" | tr -d ' ')
        log "  [ok] node_deps: ${size} bytes (syft SPDX from pnpm-lock.yaml)"
        ((GENERATED++))
    else
        log "  [warn] syft failed on web dir — trying fallback"
        HAS_SYFT_NODE=false
    fi
else
    HAS_SYFT_NODE=false
fi

if [[ "${HAS_SYFT_NODE:-true}" == "false" ]] || [[ "$HAS_SYFT" != "true" ]]; then
    # Fallback: parse package.json
    if [[ -f "${PROJECT_ROOT}/apps/web/package.json" ]]; then
        python3 -c "
import json
from pathlib import Path

pkg = json.loads(Path('${PROJECT_ROOT}/apps/web/package.json').read_text())
packages = []
for dep_type in ['dependencies', 'devDependencies']:
    for name, version in pkg.get(dep_type, {}).items():
        clean_version = version.lstrip('^~>=<')
        packages.append({
            'SPDXID': f'SPDXRef-Package-{name.replace(\"/\", \"-\").replace(\"@\", \"\")}-{clean_version}',
            'name': name,
            'versionInfo': clean_version,
            'downloadLocation': f'https://www.npmjs.com/package/{name}/v/{clean_version}',
            'supplier': 'NOASSERTION',
            'licenseDeclared': 'NOASSERTION',
        })

doc = {
    'spdxVersion': 'SPDX-2.3',
    'dataLicense': 'CC0-1.0',
    'SPDXID': 'SPDXRef-DOCUMENT',
    'name': 'ekamcore-node-deps',
    'documentNamespace': 'https://ekamcore.dev/sbom/node-deps',
    'creationInfo': {
        'created': '${TIMESTAMP}',
        'creators': ['Tool: ekamcore-sbom-generator-fallback'],
        'comment': f'Parsed from package.json. {len(packages)} packages found.'
    },
    'packages': packages
}
with open('${NODE_OUTPUT}', 'w') as f:
    json.dump(doc, f, indent=2)
print(f'  [ok] node_deps: {len(packages)} packages from package.json (fallback)')
"
        ((GENERATED++))
    else
        log "  [fail] package.json not found at apps/web/package.json"
        ((FAILED++))
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────

log ""
log "============================================================"
log "  Generated: ${GENERATED} SBOM files"
log "  Failed: ${FAILED}"
log "  Output: ${OUTPUT_DIR}/"
ls -la "$OUTPUT_DIR"/*.json 2>/dev/null | awk '{print "    " $NF " (" $5 " bytes)"}'
log "============================================================"

[[ "$FAILED" -gt 0 ]] && exit 1
exit 0
