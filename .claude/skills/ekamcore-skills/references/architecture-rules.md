# Architecture Rules Reference

## Security Rules
- TLS on all external traffic (Caddy auto-cert).
- JWT RS256, 15min expiry. Refresh token single-use rotation (replay = revoke entire session).
- CSRF double-submit cookie on POST/PATCH/DELETE. Exempt: /auth/login, /health.
- Brute-force: delay at 3/5/10 failures (1s/5s/30s). Lockout at 20 within 1hr. Audit log all attempts.
- Biometric encrypted at rest (pgcrypto AES-256, key from Keychain). Hard-delete on consent revocation.
- No secrets in files/env. All in macOS Keychain. Injected at runtime by manager app.
- Parameterized queries only. Pydantic input validation. Pack output sanitized (bleach).
- Prompt injection defense: XML delimiters around user content; system prompt says ignore instructions in data.

## Error Handling
- Response: `{error_code, message, detail, correlation_id}`
- Namespaces: AUTH_*, ADMIN_*, WORKSPACE_*, CSRF_*, VALIDATION_*, RESOURCE_*, PERSON_*, PHOTO_*, FILE_*, SOURCE_*, QUERY_*, WRITE_*, SYSTEM_*, INGESTION_*
- Client maps error_code → user text via `errorMessages.ts`. Never show raw API message.
- 401 → auto-refresh. 429 → wait + retry. 500 → generic msg + correlation_id.

## Rate Limits
| Group | Limit | Key |
|---|---|---|
| Auth endpoints | 10/min | IP |
| POST /api/v1/query | 30/min | User |
| Write endpoints (reminders, events, sources, people ops) | 10/min | User |
| All GET endpoints | 120/min | User |

## Key Architectural Decisions
- workspace_id on every content table (AD-10, AD-15). SQL-level filtering always.
- Qdrant workspace_id payload filter on every query (AD-16).
- UUID v7 for all PKs (AD-14). Time-sortable, globally unique.
- Deterministic-first query routing (AD-23). Steps 1-2 = no LLM. Steps 4-5 = LLM.
- Card registry pattern (AD-24). TodayCardSource.produce_cards() interface.
- PostgreSQL is source of truth for graph state (AD-19). Qdrant is derived.
- Priority queue with preemption (AD-13). P1 interactive preempts P3/P4 background via Redis.
- Defense in depth (AD-29). Every data path has 2+ security controls.
