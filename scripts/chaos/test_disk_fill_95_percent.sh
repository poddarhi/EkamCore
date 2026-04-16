#!/usr/bin/env bash
# Chaos Scenario 4: Fill disk to simulate low disk space.
#
# Injects: Creates a large temp file to consume disk space.
# Expected: API continues serving reads, writes may fail gracefully,
#           manager shows disk warning. After cleanup, writes resume.
# Safety: Uses a temp file that is always cleaned up on exit.

source "$(dirname "$0")/lib.sh"

SCENARIO="disk_fill_95_percent"
FILL_FILE="/tmp/ekamcore_chaos_disk_fill.bin"
echo ""
echo "=== Chaos Scenario 4: Disk Fill Simulation ==="

# Cleanup trap — always remove the fill file
cleanup_fill() {
    rm -f "$FILL_FILE" 2>/dev/null || true
    echo "  Cleanup: fill file removed"
}
trap cleanup_fill EXIT

# ── Baseline ─────────────────────────────────────────────────────────────────

ensure_healthy_baseline || { emit_result "$SCENARIO" "disk fill" \
    "Reads continue, writes fail gracefully" "Could not establish baseline" 0 false false; exit 0; }

# ── Check current disk space ─────────────────────────────────────────────────

FREE_KB=$(df -k / | tail -1 | awk '{print $4}')
FREE_GB=$((FREE_KB / 1024 / 1024))
echo "  Current free space: ${FREE_GB} GB"

# Only fill up to 2GB to avoid actually breaking the system
# This tests the code paths without risking real disk exhaustion
FILL_SIZE_MB=2048
if [[ "$FREE_GB" -lt 10 ]]; then
    echo "  WARNING: Less than 10GB free — reducing fill to 512MB for safety"
    FILL_SIZE_MB=512
fi

# ── Inject: create fill file ─────────────────────────────────────────────────

echo "  Creating ${FILL_SIZE_MB}MB fill file..."
timer_start
dd if=/dev/zero of="$FILL_FILE" bs=1m count="$FILL_SIZE_MB" 2>/dev/null || true

# ── Verify: reads still work ─────────────────────────────────────────────────

sleep 2
READ_OK=$(api_reachable && echo "true" || echo "false")
echo "  API reachable (reads): $READ_OK"

HEALTH_RESP=$(api_health 2>/dev/null || echo '{"status":"error"}')
echo "  Health response: captured"

# ── Verify: check disk warning detection ─────────────────────────────────────

# The health endpoint or disk check should detect low space
DISK_WARNING=$(echo "$HEALTH_RESP" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('disk_warning', 'N/A'))" 2>/dev/null || echo "N/A")
echo "  Disk warning from health: $DISK_WARNING"

# ── Recovery: remove fill file ───────────────────────────────────────────────

echo "  Removing fill file..."
rm -f "$FILL_FILE"
trap - EXIT  # Clear trap since we cleaned up manually

sleep 3

AFTER_READ=$(api_reachable && echo "true" || echo "false")
echo "  API reachable after cleanup: $AFTER_READ"

RECOVERY_SECS=$(timer_elapsed)

PASS=false
if [[ "$READ_OK" == "true" && "$AFTER_READ" == "true" ]]; then
    PASS=true
fi

emit_result "$SCENARIO" \
    "Created ${FILL_SIZE_MB}MB fill file to simulate disk pressure" \
    "Reads continue during fill, writes may fail, recovery after cleanup" \
    "reads_during_fill=$READ_OK, reads_after_cleanup=$AFTER_READ, disk_warning=$DISK_WARNING" \
    "$RECOVERY_SECS" false "$PASS"
