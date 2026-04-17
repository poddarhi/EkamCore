# Changelog

All notable changes to EkamCore are documented in this file.
Format follows [Conventional Commits](https://www.conventionalcommits.org/).

## [1.0.0] — 2026-04-17

### Features

#### Phase 0 — Foundation (Sprint 1-2)
- Docker Compose stack with 10 services + native Ollama
- PostgreSQL 16 with UUID v7, soft delete, workspace isolation
- FastAPI scaffold with health checks, structured logging, error hierarchy
- JWT RS256 auth with refresh rotation, brute-force protection, CSRF
- Redis 4-database allocation (sessions, queue, paperless, cache)
- Qdrant 3 collections (document, photo, face embeddings)
- React + Vite + TypeScript web scaffold with design system
- React Native mobile scaffold with ConnectivityManager
- CI/CD pipeline with lint, typecheck, test, Docker build
- Alembic migration framework with initial schema

#### Phase 1 — Core Features (Sprint 3-6)
- Calendar, Reminders, Contacts import with upsert
- Today card assembly with priority scoring
- Recap (daily/weekly) with date navigation
- Source CRUD with registration and soft-delete
- Deterministic query routing (50+ regex patterns)
- Exact text search with type filters and pagination
- Write-through reminder creation
- Web: Today page, Recap page, Search page, Sidebar navigation
- Resource controller with priority slots and thermal awareness
- Append-only audit logging

#### Phase 2 — Intelligence (Sprint 7-10)
- PaperlessNGX integration (REST client, sync scheduler, webhook)
- Document ingestion pipeline (chunking, embedding, Qdrant upsert)
- Photo ingestion (EXIF extraction, hash dedup, thumbnail generation)
- Semantic search via Qdrant with payload pre-filtering
- LLM grounded QA (phi3:mini + llama3.1:8b via Ollama)
- Query classification and 5-step processing flow
- Backup/restore (pg_dump + Qdrant snapshots + config)
- Web: file browser, photo gallery, query interface, settings pages
- Mobile: search types, connectivity config, API type definitions

#### Phase 3 — People & Packs (Sprint 11-14)
- Face detection (InsightFace buffalo_l, encrypted embeddings)
- Face clustering (incremental assignment, batch recluster)
- People Graph (trusted persons, candidate scoring, merge/split)
- Review queue (confirm/reject/skip with confidence badges)
- Person-context queries (graph-augmented search)
- PLA Pack SDK (manifest loader, capability registry, sandbox runner)
- PLA workflows: follow-up suggestions, weekly summary, relationship reminders
- Pack scheduler with asyncio cron loops
- Web: People list, PersonDetail, ReviewQueue, PackSettings
- Security audit, accessibility audit, ML eval baselines

#### Phase 4 — Manager & Release (Sprint 15-16)
- Manager app (Tauri 2): setup wizard, dashboard, watchdog, diagnostics
- macOS integration: launchd auto-start, backup scheduling, Keychain secrets
- Update/rollback: 8-step atomic flow with pre-update snapshot
- Mobile iOS app: ApiClient, biometric auth, SQLCipher cache, 13 screens
- User documentation: 34 MkDocs pages across 12 sections

### Performance
- HTTP connection pooling for Ollama (llm_client + embedder)
- Redis caching for Today card assembly (60s TTL)
- Database pool_recycle tuning and TrustedPerson indexes
- Batch embedding generation in document ingestion
- 21/21 ART-16 benchmarks PASS

### Tests
- 7 chaos test scenarios with automated recovery
- 72-hour soak test orchestrator with consistency checker
- Pen test checklist (25 checks / 9 categories)
- 11 Detox E2E specs for mobile (~45 cases)
- 1,158 Python + 55 Rust + 13 mobile unit tests
- 104 stories in test traceability matrix

### Security
- Security hardening report (ART-14 §19)
- 3 DR recovery scripts (post-power-outage, disk-full, model-reload)
- SBOM generation (Syft SPDX) + license audit + image pin verification

### CI/CD
- Release pipeline: 9-step workflow (validate → test → build → scan → SBOM → DMG → changelog → package → release)
- Nightly: full tests + manager check + chaos smoke + mobile E2E
- Weekly: security scans + SBOM + license audit

### Documentation
- User guide: 34 pages, 12 sections (MkDocs Material)
- DR Runbook: 7 automated recovery procedures
- Performance optimization report
- ML eval final report
- ART coverage audit (28 ARTs reviewed)
- Release candidate gate report

[1.0.0]: https://github.com/ekamcore/ekamcore/releases/tag/v1.0.0
