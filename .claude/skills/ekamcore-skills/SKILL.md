---
name: ekamcore
description: Master skill for EkamCore — a private, local-first life assistant on Apple silicon Mac. Use for ANY EkamCore task. Routes to sub-skills (backend, frontend, mobile, infrastructure, ml-ai, manager-app). Always read this first when working on EkamCore code.
---

# EkamCore Master Skill

## What is EkamCore
Privacy-first local life assistant on always-on Apple silicon Mac. Connects files, photos, contacts, calendars, reminders via local AI. No cloud, no telemetry, no external APIs.

**Stack**: Tauri 2 (Rust) manager, FastAPI (Python) API + workers, PostgreSQL 16, Qdrant, Ollama, Redis, Caddy, React (web), React Native (mobile).

## GOLDEN RULES — Every rule prevents a critical bug class

1. **Workspace isolation**: EVERY DB query includes `WHERE workspace_id = ANY(:ws_ids)`. EVERY Qdrant query includes workspace_id payload filter.
2. **No raw SQL**: SQLAlchemy ORM or parameterized `text()` only. Zero string concatenation.
3. **Structured errors**: Use `api/errors.py` hierarchy. Always include `error_code`. Never bare `HTTPException`.
4. **No PII in logs**: Never log query text, file content, names, emails, passwords, tokens, embeddings. Only: correlation_id, error_code, status, path, user_id, workspace_id, latency_ms.
5. **Feature flags**: New endpoints need `require_flag()`. New UI pages need `useFlag()`. Registry: `config/feature-flags.json`.
6. **Auth everywhere**: All endpoints except `/health` and `/auth/login` need `Depends(get_current_user)`. POST/PATCH/DELETE also need CSRF.
7. **UUID v7**: All PKs via `gen_uuid_v7()`. Never auto-increment, never UUID v4.
8. **Soft delete**: `deleted_at = now()`. Never hard-delete except biometric on consent revocation. Filter `WHERE deleted_at IS NULL`.
9. **Tests required**: Every new endpoint/service/component needs tests. Coverage must not decrease.
10. **Conventional Commits**: `type(scope): description`. Types: feat/fix/docs/test/chore/ci/refactor/perf. Scopes: api/web/mobile/manager/infra/openapi/alembic.

## Monorepo Layout
```
ekamcore/
  api/                  # Python FastAPI — routers/, services/, db/models/, schemas/, middleware/, workers/, packs/, tests/
  web/                  # React+Vite+TS — src/design-system/, src/pages/, src/components/, src/contexts/, src/api/
  mobile/               # React Native TS — src/screens/, src/services/, src/navigation/, src/api/
  manager/              # Tauri 2 — src-tauri/src/ (Rust), src/ (React)
  openapi/openapi.yaml  # API contract source of truth
  alembic/versions/     # Numbered migrations
  infrastructure/       # Caddy, backup, chaos scripts
  scripts/              # Dev utilities, benchmarks
  tests/                # integration/, e2e/, e2e-mobile/, fixtures/
  config/               # feature-flags.json, quality-config.json, prompt-config.json
  docker-compose.yml    # 9 services: postgres, redis, qdrant, ollama, api, workers, web, proxy, migrate
  Makefile              # All dev commands
```

## Sub-Skill Routing

| Working on... | Read this skill | Also read these references |
|---|---|---|
| Python in `api/` (routes, services, models, workers) | `backend/SKILL.md` | `api-contract-summary.md` + `db-schema-reference.md` |
| React/TS in `web/` (pages, components) | `frontend/SKILL.md` | `design-tokens-reference.md` + `api-contract-summary.md` |
| React Native in `mobile/` | `mobile/SKILL.md` | `design-tokens-reference.md` + `api-contract-summary.md` |
| Docker, CI/CD, Caddy, Makefile | `infrastructure/SKILL.md` | — |
| Ollama, embeddings, prompts, face pipeline | `ml-ai/SKILL.md` | `db-schema-reference.md` |
| Tauri/Rust in `manager/` | `manager-app/SKILL.md` | — |
| A story by ID (e.g. S03-001) | `references/sprint-story-index.md` first → then workstream skill | — |

## Phases
- **Phase 0** (S1-2): Docker, schema, API scaffold, auth, CI/CD
- **Phase 1** (S3-6): Today, Recap, Search, Calendar/Reminders/Contacts import, manager setup
- **Phase 2** (S7-10): File ingestion, embeddings, semantic search, photos, LLM query, backup
- **Phase 3** (S11-14): Face clustering, People Graph, PLA Pack, soak test, pen test
- **Phase 4** (S15-16): Perf optimization, chaos tests, docs, release

## Response Envelope (all interactive endpoints)
```json
{"answer_text": "str|null", "confidence_level": "deterministic|high|medium|low",
 "sources": [{"type":"file|contact|event|reminder|photo|person","id":"uuid","title":"str","relevance":0.95}],
 "cards": [{"type":"event|reminder|person|file|photo|status|suggestion|pack","id":"uuid","priority_score":0.85,"source_ids":[],"payload":{}}],
 "suggested_actions": [{"action_type":"str","label":"str","payload":{}}],
 "metadata": {"query_path":"deterministic|semantic|small_model|large_model","latency_ms":150,"is_partial":false,"cache_hint":{"ttl_seconds":300}}}
```

## Git
- Branch: `feature/{story-id}-{desc}` or `fix/{story-id}-{desc}`
- Squash merge. Delete after merge. PR must have Story ID + description + test instructions.
