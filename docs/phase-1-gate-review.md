# Phase 1 Gate Review — EkamCore

**Review date:** 2026-04-09  
**Reviewer:** Arpan Korat  
**Branch:** development  
**Result:** PASSED — advancing to Phase 2

---

## Story Completion (Sprints 3–6)

| Story | Title | Status | Notes |
|---|---|---|---|
| S03-001 [CP] | Calendar import | ✅ Done | EventKit bridge + internal ingest API + calendar_events table |
| S03-002 [CP] | Reminders import | ✅ Done | Reminders ingest + write-through POST /reminders |
| S03-003 [CP] | Today card assembly | ✅ Done | CalendarCardSource + ReminderCardSource + StatusCardSource, priority scoring |
| S03-005 [CP] | Manager setup wizard | ✅ Done | 8-step wizard: hardware→disk→docker→pull→migrate→admin→sources→tailscale |
| S03-006 | Startup sequence | ✅ Done | 15-step health-check polling with timeout handling |
| S04-001 [CP] | Resource controller | ✅ Done | P1–P4 priority, Redis pub/sub pause signal, thermal awareness |
| S04-002 [CP] | Web Today view | ✅ Done | SWR fetch, card rendering, empty/error states, accessibility |
| S04-004 | Mobile cached Today | ✅ Done | SQLCipher cache, connectivity banners, FlatList rendering |
| S04-005 | Watchdog supervisor | ✅ Done | 30s health poll, auto-restart 5×, macOS notification on escalation |
| S05-001 [CP] | Deterministic query routing | ✅ Done | 5-step routing: deterministic → exact search → semantic → small model → large model |
| S05-002 | Exact search | ✅ Done | Full-text search over calendar_events, reminders, contacts |
| S05-003 | Write-through reminders | ✅ Done | POST /api/v1/reminders → PG + manager bridge |
| S05-004 | Manager health dashboard | ✅ Done | Real-time resource metrics dashboard |
| S05-006 | Mobile auth service types | ✅ Done | Auth service type definitions and flow documentation |
| S06-001 | Recap page (web) | ✅ Done | Daily/weekly toggle, date navigation, SWR fetch |
| S06-002 | Mobile Recap placeholder | ✅ Done | RecapPeriod types, RecapResponse interfaces, RecapScreen docs |
| S06-003 | Diagnostics export | ✅ Done | GET /api/v1/internal/diagnostics/export with PII stripping |
| S06-004 | All deterministic patterns | ✅ Done | 50+ deterministic query variations |
| S06-005 | FSEvents monitoring | ✅ Done | POST /api/v1/internal/fs/event + GET /api/v1/internal/fs/status |
| S06-006 | Phase 1 integration tests | ✅ Done | 7 end-to-end scenarios, 7/7 passing |

**Total:** 20/20 Phase 1 stories complete.

---

## Acceptance Criteria Checklist

### Auth & Security
- [x] Login returns JWT access token (15-min) + HttpOnly refresh cookie (7-day)
- [x] Refresh rotates both tokens; replay detection revokes all user sessions
- [x] Logout writes jti to Redis blocklist; subsequent requests return 401
- [x] CSRF double-submit cookie enforced on all POST/PATCH/DELETE endpoints
- [x] Brute-force: 20 consecutive failures → 423 ACCOUNT_LOCKED; success clears counter
- [x] All endpoints (except /health, /auth/login) require `Authorization: Bearer <token>`

### Data & Workspace Isolation
- [x] All DB queries include `workspace_id` filter — confirmed by workspace isolation test
- [x] User A cannot read User B's events, reminders, or sources
- [x] Soft-delete pattern (`deleted_at`) used throughout; no hard deletes

### Calendar & Reminders
- [x] Calendar ingest is idempotent (re-ingest same event → 0 inserted, 1 updated/unchanged)
- [x] Overdue reminders surface at top of /today with priority_score ≥ 0.80
- [x] Write-through reminder creation visible immediately on /today

### Today Endpoint
- [x] Cards sorted descending by priority_score
- [x] Response conforms to ResponseEnvelope schema (answer_text, confidence_level, sources, cards, suggested_actions, metadata)
- [x] metadata.query_path populated (deterministic / semantic / small_model / large_model)

### Search & Query Routing
- [x] Deterministic patterns matched without hitting Ollama
- [x] Fallback chain: deterministic → exact search → semantic (Qdrant) → LLM
- [x] Empty query returns graceful empty response (not 500)

### Internal APIs (Manager Integration)
- [x] POST /api/v1/internal/ingest/calendar — no auth, workspace_id in body
- [x] POST /api/v1/internal/ingest/reminders — no auth, workspace_id in body
- [x] POST /api/v1/internal/fs/event — filesystem event notification
- [x] GET /api/v1/internal/fs/status — filesystem monitoring status
- [x] GET /api/v1/internal/diagnostics/export — PII-stripped diagnostics bundle

### Error Handling
- [x] All errors use structured envelope: `{"error_code": "...", "message": "...", "details": {}}`
- [x] No bare HTTPException usage
- [x] No PII in log output

---

## Test Results

| Suite | Count | Result |
|---|---|---|
| API unit tests | 413 | ✅ 413 passed |
| Phase 1 integration tests (E2E) | 7 | ✅ 7 passed |
| Web unit tests | — | Pre-existing Jest config issue (unrelated to Phase 1) |
| Mobile unit tests | — | Pre-existing Jest config issue (unrelated to Phase 1) |

Integration test scenarios:
1. `test_full_auth_flow` — login → refresh → logout → revoked token 401 ✅
2. `test_calendar_to_today_flow` — ingest events → appear on /today ✅
3. `test_reminders_overdue_flow` — overdue priority, searchable, write-through ✅
4. `test_query_to_search_fallback` — deterministic → fallback → empty ✅
5. `test_workspace_isolation` — data never crosses workspace boundaries ✅
6. `test_csrf_protection` — missing/wrong/correct CSRF on write endpoints ✅
7. `test_brute_force_lockout` — 20 failures → 423, success clears counter ✅

---

## Performance Snapshot

Measured via in-test timing (httpx ASGITransport, local PostgreSQL + Redis):

| Endpoint | p50 | Notes |
|---|---|---|
| POST /auth/login | ~80ms | Argon2id (time_cost=3, mem=64MB) dominates |
| GET /today | ~15ms | Deterministic path, warm PG connection |
| POST /ingest/calendar (2 events) | ~8ms | Bulk upsert |
| POST /reminders | ~12ms | Write-through + audit log |
| GET /search?q=... (exact) | ~10ms | FTS index scan |

Formal benchmarks (p95 at 50 concurrent users) to be run in Phase 2 pre-release via `scripts/benchmark_*.py`.

---

## Known Issues & Tech Debt

| ID | Description | Severity | Phase |
|---|---|---|---|
| TD-001 | Mobile Jest preset `react-native` not found — test runner broken | Low | Phase 2 |
| TD-002 | Coroutine warnings in reminders rate-limiter mock (`pipe.incr`/`pipe.expire` never awaited) | Low | Phase 2 |
| TD-003 | Web unit test coverage not measured (Jest config issue) | Low | Phase 2 |
| TD-004 | `asyncio_default_fixture_loop_scope = "session"` requires `pytestmark` in integration tests — document in CONTRIBUTING | Low | Phase 2 |

---

## Phase 2 Readiness

Phase 2 begins with Sprint 7: Paperless document sync and semantic search.

Prerequisites confirmed:
- [x] Qdrant collection initialized (`document_embeddings` 768-dim, `face_embeddings` 512-dim)
- [x] Ollama running on host, accessible from API container
- [x] Redis queue DB (db=1) reserved for ARQ workers
- [x] Ingestion state machine (discovery → fingerprint → metadata) implemented (S02-003)
- [x] Workspace isolation enforced at DB and Qdrant query layer
- [x] Audit log infrastructure in place
- [x] Feature-flag middleware in place for gating Phase 2 features

Next stories: S07-001 (Paperless API client), S07-002 (document sync + embeddings), S07-003 (hybrid semantic search).
