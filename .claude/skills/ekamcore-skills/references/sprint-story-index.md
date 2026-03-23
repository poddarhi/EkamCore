# Sprint Story Index (from ART-02)

Use this reference to find the specification for any story by ID. Then load the appropriate workstream skill.

## Sprint 1 (Weeks 1-2) — Phase 0
| Story | Title | Workstream | Key Spec |
|---|---|---|---|
| S01-001 [CP] | Docker Compose full stack | infrastructure | 9 containers, health checks, resource limits, ekamcore-net |
| S01-002 [CP] | PostgreSQL initial schema | backend | Alembic 001_initial_schema. All system tables + files + ingestion_states + audit_log |
| S01-003 [CP] | OpenAPI 3.1 spec | backend | openapi/openapi.yaml covering all endpoints. Generate TS+Python clients |
| S01-004 [CP] | CI/CD pipeline | infrastructure | .github/workflows/ci.yml. lint+typecheck+test+integration-build |
| S01-006 [CP] | FastAPI scaffold | backend | app factory, health endpoint, SQLAlchemy session, Pydantic config, middleware |
| S01-007 | Caddy reverse proxy | infrastructure | Caddyfile: /api/*->api:8420, /*->web:3000. TLS auto-cert |
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
| Story | Title | Workstream |
|---|---|---|
| S07-001 [CP] | File text extraction | backend |
| S07-002 [CP] | Embedding generation | ml-ai+backend |
| S07-003 [CP] | Semantic search | backend+ml-ai |
| S07-004 | OCR pipeline | backend |
| S08-001 [CP] | Photo metadata + thumbnails | backend |
| S08-004 | Automated daily backup | infrastructure |

## Sprint 9-10 (Weeks 17-20) — Phase 2
| Story | Title | Workstream |
|---|---|---|
| S09-001 [CP] | LLM grounded QA (Steps 3-5) | backend+ml-ai |
| S09-002 | Mobile full query+search | mobile |
| S10-001 | Mobile accessibility | mobile |
| S10-002 | Error taxonomy standardization | backend+frontend+mobile |

## Sprint 11-12 (Weeks 21-24) — Phase 3
| Story | Title | Workstream |
|---|---|---|
| S11-001 [CP] | Biometric consent flow | backend+frontend+mobile |
| S11-002 [CP] | Face detection+embedding | ml-ai |
| S11-003 | HDBSCAN clustering + candidates | ml-ai+backend |
| S12-001 [CP] | People Graph review queue | backend+frontend+mobile |
| S12-002 | Merge/split/undo | backend |

## Sprint 13-14 (Weeks 25-28) — Phase 3
| Story | Title | Workstream |
|---|---|---|
| S13-001 [CP] | PLA Pack core workflows | backend |
| S13-002 | Skill execution sandbox | backend |
| S13-003 | 72-hour soak test | infrastructure |

## Sprint 15-16 (Weeks 29-32) — Phase 4
| Story | Title | Workstream |
|---|---|---|
| S15-001 | Performance optimization | backend+ml-ai |
| S15-002 | Chaos testing all scenarios | infrastructure |
| S16-001 | User documentation | (technical writer) |
| S16-002 | Release candidate validation | infrastructure |

[CP] = Critical Path. Delay moves project end date.
