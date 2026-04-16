# Sprint Story Index (from ART-02)

Use this reference to find the specification for any story by ID. Then load the appropriate workstream skill.

## Sprint 1 (Weeks 1-2) — Phase 0
| Story | Title | Workstream | Key Spec |
|---|---|---|---|
| S01-001 [CP] | Docker Compose full stack | infrastructure | 9 containers + Ollama native, health checks, resource limits, ekamcore-net |
| S01-002 [CP] | PostgreSQL initial schema | backend | Alembic 001_initial_schema. All system tables + files + ingestion_states + audit_log |
| S01-003 [CP] | OpenAPI 3.1 spec | backend | openapi/openapi.yaml covering all endpoints. Generate TS+Python clients |
| S01-004 [CP] | CI/CD pipeline | infrastructure | .github/workflows/ci.yml. lint+typecheck+test+integration-build |
| S01-006 [CP] | FastAPI scaffold | backend | app factory, health endpoint, SQLAlchemy session, Pydantic config, middleware |
| S01-007 | Caddy reverse proxy | infrastructure | Caddyfile: /api/*->api:8420, /paperless/*->paperless:8000, /*->web:3000. TLS auto-cert |
| S01-008 | Qdrant collection init | backend+ml-ai | document_embeddings(768), face_embeddings(512). Idempotent init in lifespan |

## Sprint 2 (Weeks 3-4) — Phase 0
| Story | Title | Workstream | Key Spec |
|---|---|---|---|
| S02-001 [CP] | Auth: login/refresh/logout | backend | argon2id, RS256 JWT, refresh rotation, session in PG+Redis |
| S02-002 | Brute-force protection | backend | Redis rate limiter. Progressive delay. Lockout at 20. Audit log |
| S02-003 [CP] | Ingestion state machine | backend | discovery→fingerprint→metadata. Per-file isolation. Idempotent stage transitions |
| S02-004 | Design system tokens | frontend | Figma + tokens.css + tailwind.config.ts + core components (Button, Card, Input, Badge, StatusIndicator) |
| S02-005 [CP] | Performance baseline | infrastructure+ml-ai | Benchmark scripts for PG, Qdrant, Ollama, Redis, cold start |
| S02-007 | CSRF protection | backend | Double-submit cookie. X-CSRF-Token header. Session-bound |
| S02-009 | Web scaffold + design system | frontend | React+Vite+TS. Storybook. Design system components |
| S02-010 | Mobile scaffold | mobile | React Native. ConnectivityManager (6 states). Tab navigator. Login screen |

## Sprint 3-4 (Weeks 5-8) — Phase 1
| Story | Title | Workstream | Key Spec |
|---|---|---|---|
| S03-001 [CP] | Calendar import | backend+manager-app | EventKit bridge (Rust) → internal API → calendar_events table |
| S03-002 [CP] | Reminders import | backend+manager-app | Same pattern for reminders |
| S03-003 [CP] | Today card assembly | backend | CalendarCardSource + ReminderCardSource + StatusCardSource. Priority scoring |
| S03-005 [CP] | Manager setup wizard | manager-app+frontend | 8 steps: hardware→disk→docker→pull→migrate→admin→sources→tailscale |
| S03-006 | Startup sequence | manager-app | 15 steps per ArchSpec 4.2. Health check polling. Timeout handling |
| S04-001 [CP] | Resource controller | backend | P1-P4 priority. Redis pub/sub pause signal. Thermal awareness |
| S04-002 [CP] | Web Today view | frontend | SWR fetch, card rendering, empty/error states, accessibility |
| S04-004 | Mobile cached Today | mobile | SQLCipher cache, connectivity banners, FlatList rendering |
| S04-005 | Watchdog supervisor | manager-app | 30s health poll. Auto-restart 5x with backoff. macOS notification on escalation |

## Sprint 5-6 (Weeks 9-12) — Phase 1
| Story | Title | Workstream |
|---|---|---|
| S05-001 [CP] | Deterministic query routing | backend |
| S05-002 | Exact search | backend |
| S05-003 | Write-through reminders | backend+manager-app |
| S05-004 | Manager health dashboard | manager-app+frontend |
| S06-004 | All deterministic patterns | backend |
| S06-005 | FSEvents monitoring | backend+manager-app |

## Sprint 7-8 (Weeks 13-16) — Phase 2
| Story | Title | Workstream | Key Spec |
|---|---|---|---|
| S07-001 [CP] | PaperlessNGX API Client | backend | api/services/paperless/client.py using httpx. Pull documents, correspondents, tags. |
| S07-002 [CP] | Paperless Document Sync + Embedding Generation | ml-ai+backend | Periodic worker: pull from Paperless, chunk, embed via Ollama nomic-embed-text, store in Qdrant |
| S07-003 [CP] | Hybrid Semantic Search | backend+ml-ai | Qdrant semantic + Paperless full-text. Merge and re-rank results. |
| S07-004 | Paperless Correspondent → People Graph Mapping | backend | Map Paperless correspondents to People Graph entries. Bridge service. |
| S08-001 [CP] | Photo metadata + thumbnails | backend |
| S08-004 | Automated daily backup | infrastructure |
| S08-006 (NEW) | Paperless Setup in Manager Wizard | manager-app | Add Paperless health check step to manager setup wizard (S03-005). Show consume dir path. |

## Sprint 9-10 (Weeks 17-20) — Phase 2
| Story | Title | Workstream |
|---|---|---|
| S09-001 [CP] | LLM grounded QA (Steps 3-5) | backend+ml-ai |
| S09-002 | Mobile full query+search | mobile |
| S10-001 | Mobile accessibility | mobile |
| S10-002 | Error taxonomy standardization | backend+frontend+mobile |

## Sprint 11 (Weeks 21-22) — Phase 3 — SHIPPED
| Story | Title | What shipped |
|---|---|---|
| S11-001 [CP] | Phase 3 activation | Alembic 013, face_detections / face_clusters / trusted_persons tables, Qdrant face_embeddings with mandatory workspace_id payload index, Fernet helpers, three-gate `face_pipeline_active(flag + key + consent)` |
| S11-002 [CP] | ConsentService | `is_consent_active / grant / revoke` with 60s Redis cache, audit_log writes, atomic revoke+hard_delete contract (ART-15 §3) |
| S11-003 [CP] | Consent API + hard-delete | GET/POST/DELETE `/api/v1/settings/face-clustering/consent`, CSRF + 10/min rate limit, synchronous transactional hard_delete (Qdrant-first, PG cascade) |
| S11-004 [CP] | Consent dialog UI | `ConsentDialog` with scroll-to-bottom enforcement, `PhotoIntelligenceSettings` state machine, two-step disable, apiFetch CSRF auto-send fix |
| S11-005 [CP] | InsightFace singleton | `FaceModel` fail-closed load, SCRFD-10g + ArcFace-R100 (buffalo_l), PII-safe log whitelist, SHA-256 download script |
| S11-006 [CP] | Face ingestion stage | `FACE_DETECTION` pipeline stage, `process_photo_for_faces` worker with in-worker consent re-check + idempotent wipe + workspace isolation |
| S11-007 | Historical backfill | `photo_assets.face_processed_at` marker, `face_backfill_jobs` table + worker, 3 endpoints (1/hr/ws rate limit), UI progress bar + cancel |
| S11-008 | Observability | `/health` extension, `GET /api/v1/face/status`, `record_face_event/latency` metrics + flushers, admin StoragePage tile, full-pipeline PII log sweep |
| S11-009 | E2E + eval baseline | `tests/integration/test_phase3_e2e_foundation.py` (7 scenarios), `scripts/eval/eval_face_detection.py` with graceful skip, traceability matrix update |
| S11-010 | Gate review | skills + legal brief + phase-3 status doc, Sprint 12 readiness |

## Sprint 12 (Weeks 23-24) — Phase 3 — SHIPPED
Backend complete; UI lands in Sprint 13.

| Story | Title | Evidence |
|---|---|---|
| S12-001 [CP] | HDBSCAN face clustering service | `cluster_workspace`, lazy hdbscan, per-workspace params, identity preserved across runs (`apps/api/api/services/face/clustering_service.py`) |
| S12-002 [CP] | Incremental cluster assignment | `assign_face_to_cluster`, drift guard, recluster hint Redis counter (`apps/api/api/services/face/incremental_cluster.py`) |
| S12-003 | Candidate contact scoring | five-signal weighted score cached on `face_clusters.candidates_json`, batch + per-cluster API (`apps/api/api/services/face/candidate_scorer.py`) |
| S12-004 | TrustedPersons CRUD + cluster confirm/reject | seven `/api/v1/people` endpoints, audit + consent gates (`apps/api/api/routers/people.py`, `trusted_person_service.py`) |
| S12-005 | Review Queue API | `/api/v1/review-queue` list/detail/skip, score-ordered cursor pagination, per-user 24h skip Redis marker (`apps/api/api/routers/review_queue.py`, `review_queue.py`) |
| S12-006 | Merge / split / undo operations | `person_operations` undo log with inverse_payload, full round-trip undo, double-undo → 409 (`merge_service.py`, `split_service.py`, `undo_service.py`, `routers/people_operations.py`) |
| S12-007 | Graph edges Person↔Photo/Event/File | `appears_in` / `attended` edge builders, idempotent delete-then-insert per scope, per-person hooks on create/merge/split (`graph_edge_builder.py`) |
| S12-008 | E2E + ML eval baselines | 8 scenario `test_phase3_clustering_e2e.py`, synthetic clustering + scoring eval scripts in `scripts/eval/`, baselines in `eval_results/` |
| S12-009 | Gate review | skill updates + `docs/phase-3-sprint-12-status.md`, Sprint 13 readiness |

## Sprint 13 (Weeks 25-26) — Phase 3 — SHIPPED
People Graph web UI lands on top of the Sprint 12 backend.

| Story | Title | Evidence |
|---|---|---|
| S13-001 [CP] | Web foundations for People Graph | routing, TS types, API clients, SWR hooks, i18n, metrics, feature flags; stub pages gated on flag + consent (`apps/web/src/{types,api,hooks}/`, `FlagContext`) |
| S13-002 | People list page | grid/list toggle, debounced search, confidence chips, `PersonAvatar` backed by `/api/v1/people/:id/avatar`, empty state CTA (`apps/web/src/pages/people/PeopleListPage.tsx`, `components/people/PersonAvatar.tsx`, `api/services/face/avatar_service.py`) |
| S13-003 | Person detail page | tabs/rename/delete + Faces management with "remove face"; new `detach_face_service`, 6 `/people/:id/*` sub-resource endpoints, migration 019, undo handler (`routers/people.py`, `services/face/detach_face_service.py`, `pages/people/PersonDetailPage.tsx`) |
| S13-004 | Review Queue page | useReducer session cursor, Enter/R/S/N/1–5/←/→/?/Esc keyboard shortcuts, optimistic auto-advance with rollback, batch reject/skip bar, sr-only announcements (`pages/people/ReviewQueuePage.tsx`) |
| S13-005 | Merge persons modal | radio keeper picker, typeahead add-more, list-view multi-select with floating merge bar (`components/people/MergePersonsModal.tsx`, `pages/people/PeopleListPage.tsx` multi-select, `pages/people/PersonDetailPage.tsx` kebab) |
| S13-006 | Split person modal | `role=grid` face picker, `≥1 / name / leave-one-behind` client rules, Faces section select-mode + floating Split bar, `preselectedFaceIds` seed (`components/people/SplitPersonModal.tsx`, `pages/people/PersonDetailPage.tsx`) |
| S13-007 | Undo drawer + Cmd+Z | right-side drawer over `usePersonOperations(50)` with per-row summaries and Undo button, `useUndoShortcut` document-level Cmd/Ctrl+Z wired into people pages, History button on `PeopleListPage` (`components/people/UndoDrawer.tsx`, `hooks/useUndoShortcut.ts`) |
| S13-008 | Photo lightbox | full-screen viewer with measured bbox overlay, known→`/people/:id` and unknown→`/people/review?highlight_cluster=:id` navigation, new `/photos/:id/{full,faces}` endpoints, shared `resolve_workspace_with_face_consent`, PhotoCard + Photos tab integration (`components/photos/PhotoLightbox.tsx`, `routers/photos.py`, `services/face/consent_service.py`) |
| S13-009 | People in Today/Search + top-bar search | `search_trusted_persons` + `"person"` SearchType, `PersonCardSource` for Today feed, `PersonCard` in `CardRenderer`/`SearchResultCard`, `TopBarPersonSearch` typeahead with @-sigil and keyboard nav, gated on consent with graceful disabled fallback (`services/query/search.py`, `services/today/person_card_source.py`, `components/cards/PersonCard.tsx`, `components/people/TopBarPersonSearch.tsx`) |
| S13-010 | E2E plan + a11y audit scaffold | Playwright infra not yet in repo; ships `tests/e2e/README.md` + `tests/e2e/sprint13_plan.md` (full spec matrix, seed contract, flaky-test guardrails), new §9 Phase 3 pages section in `docs/ACCESSIBILITY_CHECKLIST.md`, and accurate S13-001..S13-010 mappings in `docs/test_traceability.json` |
| S13-011 | Gate review | skill file updates + `docs/phase-3-sprint-13-status.md`, Sprint 14 readiness |

## Sprint 14 (Weeks 27-28) — Phase 3 — PENDING
PLA Pack SDK and the simplified "catch-up" logic uplift.

| Story | Title | Workstream |
|---|---|---|
| S14-001 [CP] | PLA Pack manifest + execution engine | backend |
| S14-002 | Skill execution sandbox | backend |
| S14-003 | Pack cards in Today feed | backend+web |
| S14-004 | 72-hour soak test | infrastructure |

## Sprint 15-16 (Weeks 29-32) — Phase 4
| Story | Title | Workstream |
|---|---|---|
| S15-001 | Performance optimization | backend+ml-ai |
| S15-002 | Chaos testing all scenarios | infrastructure |
| S16-001 | User documentation | (technical writer) |
| S16-002 | Release candidate validation | infrastructure |

[CP] = Critical Path. Delay moves project end date.
