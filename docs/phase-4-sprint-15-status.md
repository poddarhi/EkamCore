# Phase 4 — Sprint 15 Status: SHIPPED

**Sprint:** 15 (Weeks 29-30)
**Phase:** 4 — Performance, Chaos, Manager App, Release Pipeline
**Date:** 2026-04-16
**Stories:** 12 shipped, 0 deferred

## Story Status

| Story | Title | Status | Commit | Key Deliverables |
|-------|-------|--------|--------|-----------------|
| S15-001 | Tauri 2 scaffold | SHIPPED | `037d1eb` | ContainerRuntime trait + DockerRuntime, KeychainManager (8 secrets), 10 IPC command handlers, AppState, TypeScript typed wrappers |
| S15-002 | Setup wizard | SHIPPED | `fe2f67a` | 8-step first-run wizard, Keychain secret generation (RSA-2048 JWT + 6 hex), per-service image pull progress, admin account with password validation |
| S15-003 | Dashboard + watchdog | SHIPPED | `f4ded63` | Watchdog (30s poll, exponential backoff, macOS notifications), 10-service health tiles, KPI cards, alert banners, Start/Stop All controls |
| S15-004 | Jobs + Storage + Diagnostics | SHIPPED | `dbc5edc` | Offline diagnostics ZIP (8 sections, no PII), Jobs page (4 sections, retry), Storage breakdown + cleanup, service log viewer |
| S15-005 | macOS integration | SHIPPED | `3aeef92` | Login item via launchd, backup scheduling, Keychain-to-Docker secret injection (temp .env + secure delete), Settings page with danger zone |
| S15-006 | Update/rollback | SHIPPED | `b9729c7` | 8-step atomic update, auto-rollback at steps 5/6/7, compose tag replacement, backup list with manual rollback, progress stepper UI |
| S15-007 | Performance optimization | SHIPPED | `bb2c98f` | httpx connection pooling, Redis cache for Today (60s), DB pool_recycle, TrustedPerson indexes, batch embedding generation. 21/21 benchmarks PASS |
| S15-008 | Chaos testing | SHIPPED | `4dbc388` | 7 scenarios (postgres kill, qdrant kill, sigkill all, disk fill, model corruption, network partition, concurrent load). `make chaos-test` |
| S15-009 | Release pipeline | SHIPPED | `8a8d7e3` | 9-step release.yml (validate→test→build→scan→SBOM→DMG→changelog→package→release). CI + nightly updates. `make release-check/build/package` |
| S15-010 | DR + Security + SBOM | SHIPPED | `53e456e` | 3 new DR scripts, pen test checklist (25 checks / 9 categories), security hardening report, DR runbook update |
| S15-011 | ML eval + gap audit | SHIPPED | `dac2845` | All ML targets PASS, 28 ARTs reviewed (22 full, 4 partial, 2 deferred), 1158 Python + 55 Rust tests, 98-story traceability |
| S15-012 | Gate review | SHIPPED | (this) | Skill updates, status doc, sprint verification |

## Sprint 15 Metrics

| Metric | Value |
|--------|-------|
| Rust files created | 8 new modules (2,500+ lines) |
| React pages created | 8 new pages (3,000+ lines) |
| Rust unit tests | 55 passing, 0 failing |
| Python test functions | 1,158 across 115 files |
| Chaos test scenarios | 7 validated |
| Pen test checks | ~25 automated |
| ART-16 benchmarks | 21/21 PASS |
| ML eval targets | All PASS |
| ARTs fully covered | 22/28 (4 partial acceptable, 2 deferred) |
| Traceability stories | 98 total |

## Manager App Summary (S15-001 through S15-006)

The Tauri 2 manager app is the primary deliverable of Sprint 15 — a native macOS
application that replaces CLI-only management with a GUI:

- **18 Rust modules** handling hardware detection, Docker management, Keychain secrets,
  watchdog supervision, diagnostics, launchd integration, update/rollback
- **8 React pages** providing setup wizard, dashboard, jobs, storage, diagnostics,
  updates, and settings
- **55 Rust unit tests** covering all modules
- **TypeScript compiles clean** across all pages

## Verification Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Rust compilation | `cd apps/manager/src-tauri && cargo check` | 0 errors |
| Rust tests | `cd apps/manager/src-tauri && cargo test` | 55 passed, 0 failed |
| TypeScript | `cd apps/manager && npx tsc --noEmit` | 0 errors |
| Python syntax | `python3 -c "import ast; ..."` on all changed .py files | All OK |
| Shell scripts | `bash -n` on all .sh files | All OK |
| Workflow YAML | name + on + jobs keys present | All 4 workflows valid |
| Benchmarks | `python scripts/benchmark/harness.py` | 21/21 PASS |
| Chaos | `make chaos-test` | 7/7 scenarios (requires Docker) |
| Security | `python scripts/security/pen_test_checklist.py` | All checks pass (requires API) |

## Sprint 16 Readiness

Sprint 15 completes the following Phase 4 pillars:
- Manager app: fully functional with all tabs
- Performance: optimized and benchmarked
- Chaos testing: 7 scenarios automated
- Release pipeline: 9-step workflow ready
- Security: pen test + DR + SBOM complete
- ML eval: all targets verified

**Remaining for Sprint 16:**
- S16-001: Mobile React Native scaffolding
- S16-002: User documentation (ART-28)
- S16-003: Release candidate packaging
- S16-004: Final quality gate + v1.0 tag

Phase 4 continues in Sprint 16. `current_phase` stays at 4.
