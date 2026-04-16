# Phase 3 Gate Review

**Gate date**: 2026-04-16
**Verdict**: SHIPPED — People Graph + PLA Pack SDK + person-context queries.
**Phase advance**: 3 → 4

## Stories Completed (Sprints 11-14)

| Sprint | Stories | Theme |
|---|---|---|
| 11 | S11-001..S11-010 | Biometric consent + face detection pipeline |
| 12 | S12-001..S12-009 | HDBSCAN clustering + candidate scoring + review queue backend |
| 13 | S13-001..S13-011 | People Graph web UI — all screens, keyboard shortcuts |
| 14 | S14-001..S14-013 | PLA Pack SDK + three workflows + pack card UI + person-context queries |

## Phase 3 Acceptance Criteria

- [x] Face detection pipeline consent-gated (ART-15)
- [x] Face embeddings encrypted at rest (Fernet AES-128-CBC)
- [x] Hard-delete synchronous on consent revocation
- [x] HDBSCAN clustering with per-workspace params (ART-11)
- [x] Incremental cluster assignment on photo ingestion
- [x] Cluster-to-contact candidate scoring (ART-11, ART-25)
- [x] Trusted persons CRUD with confirm/reject lifecycle
- [x] Review Queue — keyboard-driven confirmation (ART-07)
- [x] Merge / Split / Undo with inverse log (ART-11)
- [x] Graph edges: Person to Photo/Event/File (ART-11)
- [x] People List, Person Detail, Review Queue, modals, Undo drawer (ART-06/07)
- [x] Photo lightbox with face overlay + person nav (ART-07)
- [x] Person cards in Today / Search (ART-07)
- [x] Top-bar person search (ART-06)
- [x] Pack SDK: manifest, capability registry, PackContext, sandbox, scheduler (ART-13)
- [x] PLA Pack: follow-up, weekly summary (LLM), relationship reminders (ART-13)
- [x] Pack card UI with Done/Dismiss/Snooze (ART-07, ART-13)
- [x] Pack settings page (ART-21)
- [x] Notification triggers for pack runs (ART-20)
- [x] Person-context query router integration (ART-12, ART-11)
- [x] i18n for all Phase 3 features (ART-22)
- [x] WCAG AA audit — checklist §9-10 (ART-26)
- [x] E2E plan documented (Playwright infra deferred) (ART-18)
- [x] ML eval baselines: face, clustering, scoring, PLA quality (ART-25)
- [x] Security audit: sandbox, isolation, consent cascade (ART-14)

## Test Counts

| Suite | Pass | Fail | Notes |
|---|---|---|---|
| Web vitest | 112 | 10 | Same 10 pre-existing `accessibility.test.tsx` failures (axe-core devDep missing in jsdom) |
| Web tsc | clean | 0 | 0 type errors |
| Backend unit (Sprint 14) | 154 | 0 | pack_flags + pack_settings + manifest_loader + capability_registry + pack_context + pack_context_isolation + pack_runner + pack_scheduler + follow_up + weekly_summary + relationship_reminder + person_detector + pack_security |
| Backend integration | — | — | Requires live DB stack; CI-authoritative |
| Playwright E2E | — | — | Infra not installed; plans in tests/e2e/ |

## PLA Quality Eval Results

| Metric | Value | Target | Status |
|---|---|---|---|
| Follow-up precision | 1.000 | >= 0.95 | PASS |
| Follow-up recall | 0.500 | >= 0.40 (max 5/10) | PASS |
| Relationship precision | 1.000 | >= 0.90 | PASS |
| Relationship false positives | 0 | 0 | PASS |
| Weekly parse_success_rate | 0.800 | >= 0.80 | PASS |
| Weekly name_mention_rate | 1.000 | >= 0.80 | PASS |
| Overall | PASS | | |

## Legal Status

- **Consent text version**: DRAFT (sprint-11-legal-brief.md)
- **Legal Advisor sign-off**: PENDING — no returned edits received
- **Impact**: `face_clustering_enabled` must NOT be flipped to true for external users until legal sign-off. Internal testing on the developer's own workspace can continue under the draft consent since the data subject and the data controller are the same person.

## Sprint 14 Story Status

| Story | Status | Evidence |
|---|---|---|
| S14-001 Pack Infrastructure | SHIPPED | tables, flags, settings, i18n, errors |
| S14-002 Manifest + Capabilities | SHIPPED | YAML loader, capability registry |
| S14-003 PackContext | SHIPPED | scoped access, capability + consent enforcement |
| S14-004 Pack Sandbox | SHIPPED | timeout, memory, sanitization |
| S14-005 Scheduler + Lifecycle | SHIPPED | asyncio cron, health, enable/disable |
| S14-006 Follow-Up Suggestions | SHIPPED | deterministic workflow + dedup + snooze |
| S14-007 Weekly Summary | SHIPPED | LLM + fallback + dedup |
| S14-008 Relationship Reminders | SHIPPED | graph-strength + urgency + composite daily |
| S14-009 Pack Cards + Today | SHIPPED | 3 card components, acknowledgment, notifications |
| S14-010 Pack Settings Page | SHIPPED | toggles, schedule, history |
| S14-011 Person-Context Query | SHIPPED | person detection + graph augmentation |
| S14-012 E2E + Eval + Security | SHIPPED | 8 security tests, eval baseline, plans |
| S14-013 Gate Review | SHIPPED | skill updates, gate doc, phase advance |

## Known Limitations (documented, not blocking)

1. Playwright not installed — E2E coverage is plan-only.
2. Legal consent text is DRAFT — external users must not be onboarded yet.
3. APScheduler not used — asyncio loops (single-Mac sufficient).
4. Memory enforcement is advisory (RSS delta logging), not hard kill.
5. Network isolation is structural (PackContext mediation), not namespace.
6. Recap person stats not extended (S13-009 deferral).
7. Toast-action inline Undo not shipped (S13-007 deferral).
8. HEIC full-resolution transcoding deferred.
9. PLA "catch-up" card context uses simplified recent-photo logic only.
10. 10 pre-existing vitest a11y failures unrelated to Phase 3.

## Phase 4 Readiness

Phase 4 scope (ART-02): polish, performance optimization, user
documentation, Tauri manager app, mobile app, release candidate.

- [x] Skills files updated with Sprint 14 patterns
- [x] Sprint story index reflects all 4 sprints
- [x] Traceability covers S11-001..S14-013
- [x] Accessibility checklist covers §1-10
- [x] `current_phase` advanced to 4
- [ ] Playwright install story queued (first Phase 4 action)
- [ ] Legal consent sign-off (blocks external onboarding)
- [ ] Ollama models pulled (llama3.2:1b, nomic-embed-text)
