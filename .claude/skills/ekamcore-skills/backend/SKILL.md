---
name: ekamcore-backend
description: Use when writing Python backend code for EkamCore — FastAPI routes, SQLAlchemy models, Pydantic schemas, services, middleware, workers, ingestion pipeline, query routing, auth, tests, or any code in the api/ directory. Also use for Alembic migrations and background task definitions.
---

# EkamCore Backend Skill

**Always read the Master SKILL.md first.** Then read this skill for Python/FastAPI specifics.

## Project Structure
```
api/
  main.py              # FastAPI app factory with lifespan (startup: init DB, Qdrant, flags, Redis)
  config.py            # Pydantic BaseSettings from env vars
  errors.py            # Exception hierarchy (ALWAYS use these, never bare HTTPException)
  routers/             # One file per resource: auth.py, today.py, recap.py, query.py, search.py, people.py, photos.py, files.py, sources.py, admin.py, flags.py, internal.py
  services/            # Business logic. NEVER import from routers. Routers import services.
    ingestion/         # discovery.py, fingerprint.py, metadata.py, text_extraction.py, ocr.py, embedder.py, state_machine.py, pipeline.py
    query/             # router.py, patterns.py, handlers.py, semantic.py, prompts/, llm_client.py, output_parser.py, sanitizer.py, context_assembler.py
    today/             # base.py (TodayCardSource), calendar_source.py, reminder_source.py, status_source.py, assembly.py
    recap/             # generator.py
    graph/             # candidate_generator.py, operations.py (merge/split/undo)
    feature_flags.py, audit.py, resource_controller.py, write_through.py, redis.py, qdrant_init.py
  db/models/           # SQLAlchemy ORM models. One file per table.
  schemas/             # Pydantic v2 models for request/response. Match OpenAPI spec.
  middleware/          # auth.py (get_current_user), csrf.py, correlation.py (X-Correlation-ID), logging.py, feature_gate.py (require_flag)
  workers/             # ARQ/Celery task definitions. Each task: run_ingestion_pipeline, run_clustering, run_backup, etc.
  packs/pla/           # PLA Pack: manifest.yaml, workflows.py, card_source.py
  tests/unit/          # pytest. One test file per module: test_auth.py, test_today.py, etc.
```

## CRITICAL PATTERNS — Follow exactly

### Route Handler Pattern
```python
@router.get("/api/v1/{resource}", dependencies=[require_flag("{flag_key}")])
async def get_resource(
    resource_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope:
    result = await resource_service.get_by_id(resource_id, user.workspace_ids, db)
    if not result:
        raise NotFoundError(error_code="RESOURCE_NOT_FOUND", message="Not found.")
    return ResponseEnvelope(cards=[result.to_card()], confidence_level="deterministic", ...)
```

### Error Raising Pattern
```python
# CORRECT:
raise NotFoundError(error_code="PERSON_NOT_FOUND", message="Person not found.")
raise ConflictError(error_code="MERGE_SELF", message="Cannot merge a person with themselves.")
raise AuthenticationError(error_code="AUTH_TOKEN_EXPIRED", message="Session expired.")

# WRONG — NEVER DO THIS:
raise HTTPException(status_code=404, detail="Not found")
raise Exception("Something went wrong")
return {"error": "bad request"}
```

### Database Query Pattern
```python
# CORRECT — workspace filtering:
stmt = select(File).where(File.id == file_id, File.workspace_id.in_(user.workspace_ids), File.deleted_at.is_(None))

# WRONG — missing workspace filter:
stmt = select(File).where(File.id == file_id)
```

### SQLAlchemy Model Pattern
```python
class File(Base):
    __tablename__ = "files"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=gen_uuid_v7)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # ... domain columns
```

### Ingestion State Machine
Stages: DISCOVERED → FINGERPRINTED → METADATA_EXTRACTED → **FACE_DETECTION** → TEXT_EXTRACTED → OCR_COMPLETED → EMBEDDING_QUEUED → EMBEDDED → COMPLETED. Also: FAILED, SKIPPED.
FACE_DETECTION stage (S11-006) is a photo-only no-op advance in the state machine — the actual work happens in `process_photo_for_faces()` invoked by photo_pipeline after METADATA_EXTRACTED. Non-photo files pass through it as a no-op advance.
Transition: UPDATE ingestion_states SET current_stage=:new WHERE file_id=:fid AND current_stage=:expected. If 0 rows: already advanced (idempotent). `ck_ingestion_states_stage` CHECK constraint enumerates the 9 stages (see alembic 015).
Per-file error isolation: one file's failure never blocks another.

### Consent-Gated Endpoints (S11-002..008)
Face pipeline endpoints must be gated on **active consent**, NOT just on a feature flag. Two working patterns:

**Pattern A — derive workspace from user (preferred for consent-related endpoints)**
```python
# Mirrors api/routers/face_consent.py, face_backfill.py, face_status.py
def _resolve_workspace(user: CurrentUser) -> UUID:
    if not user.workspace_ids:
        raise AuthorizationError(error_code="NO_WORKSPACE", ...)
    return user.workspace_ids[0]

async def _require_consent(workspace_id: UUID, db: AsyncSession) -> None:
    if not await consent_service.is_consent_active(workspace_id, db):
        raise FaceConsentRequiredError(error_code="FACE_CONSENT_REQUIRED", ...)

@router.get("/api/v1/face/status")
async def get_status(user=Depends(get_current_user), db=Depends(get_db)):
    ws = _resolve_workspace(user)
    await _require_consent(ws, db)
    ...
```
Use this when the endpoint is logically "about the user's workspace" — guards against confused-deputy attacks via tampered query parameters.

**Pattern B — `require_face_consent` dependency (query-param workspace_id)**
```python
# api/dependencies/face_consent.py
@router.post("/api/v1/photos/faces/reindex",
             dependencies=[Depends(require_face_consent)])
async def reindex(workspace_id: UUID = Query(...), ...):
    ...
```
Use this when the endpoint is explicitly per-workspace and the caller legitimately selects the workspace via query.

**Audit trail**: every grant/revoke emits an `object_audit_log` row with `action` in:
  - `face_consent_granted`
  - `face_consent_revoked`
  - `face_data_hard_deleted`
Hard-delete runs inside the revoke transaction (ART-15 §3) — any failure rolls back the revocation.

**Error codes** (api/errors_registry.py):
  - FACE_CONSENT_REQUIRED (403)
  - CONSENT_VERSION_STALE (409)
  - BACKFILL_ALREADY_RUNNING (409)
  - BACKFILL_NOT_RUNNING (404)
  - FACE_MODEL_NOT_LOADED (503), FACE_MODEL_LOAD_FAILED (503), FACE_MODEL_INVALID_IMAGE (422)
  - FACE_HARD_DELETE_* (503 family — see hard_delete.py for failure-mode analysis)

**Rate limits** on face endpoints use Redis DB_CACHE:
  - Consent grant/revoke: 10/min/user
  - Backfill start: 1/hour/workspace
Inline pattern in router (see face_consent.py `_check_rate_limit`). Not a dependency — called explicitly.

**PII rule in face service logs**: counts, ids, durations, error_type, version strings only. Never bbox, embeddings, filenames, image bytes. Enforced by tests/test_face_logging.py, tests/security/test_face_logs_no_pii.py, and tests/integration/test_phase3_e2e_foundation.py::test_logs_pii_free_full_pipeline.

### Query Router Decision Tree
1. Regex/keyword match → deterministic SQL (no LLM, confidence=deterministic)
2. Structured filter → parameterized query (no LLM)
3. Ollama available? → if no, return search results + degraded banner
4. Simple query? → phi3:mini (5s timeout)
5. Complex query? → llama3.1:8b (15s timeout)
Fallback cascade: large→small→deterministic. Never show empty results.

### Testing
- Location: api/tests/unit/test_{module}.py
- Framework: pytest + pytest-asyncio
- Every endpoint: test happy path + auth required + workspace isolation + error cases
- Every service function: test core logic + edge cases
- Fixtures: use factories from tests/factories.py
- Run: `make test-api`

### Auth Implementation
- Password: argon2id (memory=65536, time=3, parallelism=4) via argon2-cffi
- JWT: RS256. Claims: sub(user_id), role, workspaces[], iat, exp(+15min), iss, jti
- Refresh: opaque token (secrets.token_urlsafe(32)). Stored as SHA-256 hash. Single-use.
- Session: PostgreSQL sessions table + Redis db0 cache
- CSRF: double-submit cookie. Generate: secrets.token_urlsafe(32). Verify header matches cookie.

### Logging
```python
import structlog
logger = structlog.get_logger()
logger.info("request_completed", method=method, path=path, status=status, latency_ms=latency, correlation_id=cid)
# NEVER: logger.info(f"Query: {user_query}")  ← logs personal data
```

## PaperlessNGX Integration

### Error Code
`PAPERLESS_UNAVAILABLE` → 503. Paperless being down never degrades core EkamCore queries.

### Ollama URL
`OLLAMA_URL` always uses `http://host.docker.internal:11434` (Ollama runs natively on host, not in Docker).

### PaperlessNGX API Client Pattern
```python
# api/services/paperless/client.py
import httpx

PAPERLESS_BASE = "http://ekamcore-paperless:8000/api"

async def get_documents(token: str, page: int = 1) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PAPERLESS_BASE}/documents/",
            headers={"Authorization": f"Token {token}"},
            params={"page": page},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
```

### Document Sync Worker Pattern
Periodic ARQ task (`workers/tasks/paperless_sync.py`):
1. GET `/api/documents/?ordering=-modified` from Paperless (paginated)
2. For each doc: fetch full text via `/api/documents/{id}/download/`
3. Chunk text (512 tokens, 64 overlap)
4. Embed via `http://host.docker.internal:11434` (nomic-embed-text)
5. Upsert into Qdrant `document_embeddings` collection with `workspace_id` payload filter
6. Store sync cursor in Redis

### Paperless Correspondent → People Graph Bridge
`api/services/paperless/correspondent_bridge.py`:
- Pull correspondents from Paperless API
- Fuzzy-match name against `people` table (workspace-scoped)
- Create candidate links; queue for human review via People Graph review queue (S12-001)

### Hybrid Search Pattern
```python
# Combine Qdrant semantic + Paperless full-text
async def hybrid_search(query: str, workspace_ids: list[UUID]) -> list[SearchResult]:
    semantic = await qdrant_service.search(query_embedding, workspace_ids, limit=20)
    fulltext = await paperless_client.search(query, token=get_paperless_token())
    return merge_and_rerank(semantic, fulltext)
```

## Sprint 12 backend patterns

### Review Queue Pagination (S12-005)
`api/services/face/review_queue.py::list_pending` is the canonical
example of a *score-ordered* paginated read. The cursor is the
stringified `cluster_id` of the last returned row. Sort key is
`(-top_candidate.score, str(cluster_id))` so ties break
deterministically. Pagination walks the full eligible set in memory
because per-workspace counts are bounded (a few hundred clusters max
on personal-scale data) and the scoring step requires per-row
candidate parsing anyway. Per-user skip markers
(`skipped:{user_id}:{cluster_id}` Redis keys, 24h TTL) are filtered
*before* sort so the page contents stay stable across paginations.

### Graph Edge Builder (S12-007)
`api/services/face/graph_edge_builder.py` writes
`trusted_person -> photo_asset/calendar_event/file` edges. The
idempotency pattern is **delete-then-insert** per scope:

```python
await db.execute(
    delete(GraphEdge).where(
        and_(
            GraphEdge.workspace_id == workspace_id,
            GraphEdge.from_type == "trusted_person",
            GraphEdge.from_id.in_(person_ids),
            GraphEdge.to_type == "photo_asset",
            GraphEdge.edge_type == "appears_in",
        )
    )
)
await db.flush()
# ... insert fresh edges
```

This is simpler than `ON CONFLICT DO UPDATE` and lets us recompute
per-edge metadata (strength, evidence_json) without comparing every
column. The `(from_type, edge_type)` key makes the scope unambiguous —
the builder owns *that* edge family for *those* persons and nothing
else.

Hooks: `trusted_person_service.create_from_cluster`,
`merge_service.merge_persons`, and `split_service.split_person` each
call `build_person_photo_edges(person_ids=[...])` so the graph
follows cluster membership without touching unrelated persons.

### Person Operation Audit Chain (S12-006)
Every reversible mutation writes **two** rows in the same transaction:

1. `person_operations` row via `operation_recorder.record(...)` —
   has `forward_payload` (display) and `inverse_payload` (undo state).
2. `object_audit_log` row via `audit.log_event(...)` — the standard
   compliance trail.

The split is intentional: `person_operations` is a *user-facing
history* (visible in the History tab, undoable) while `object_audit_log`
is *legal evidence* (append-only, immutable). The two log writes
must commit atomically with the state change — never write one
without the other.

Routing gotcha: when a router uses path params like `/{person_id}`,
register fixed-suffix routers (`/operations/...`, `/merge`) **before**
the parameterised ones in `main.py`, otherwise FastAPI matches
`/operations` against `/{person_id}` and returns 422 on the UUID parse.

## Sprint 13 backend patterns

### Shared face-consent guard (S13-008)
`api/services/face/consent_service.py::resolve_workspace_with_face_consent`
is the single source of truth for the "this request needs active
face consent" guard. Both the people router (S12) and the photos
router (S13-008) call it. When adding a new face-adjacent
endpoint, always go through this helper — never re-implement the
`is_consent_active` + error-copy dance, or the two routers will
drift.

### Person-scoped sub-resources (S13-003)
`api/routers/people.py` exposes a family of `/people/{person_id}/*`
reads for the detail page: `/photos`, `/files`, `/events`,
`/reminders`, `/faces`, `/faces/{fid}/thumbnail`. The pattern:

1. `_ensure_person(person_id, workspace_id, db)` runs first so a
   bad id / cross-workspace probe returns 404 before any child
   query touches the graph tables.
2. Use `graph_edges` as the denormalization layer. Photos and
   events join on
   `GraphEdge.from_type='trusted_person' AND edge_type='appears_in' | 'attended'`
   rather than re-computing membership from `face_clusters` each
   request.
3. Cursor pagination uses the child table's `id DESC` (UUID v7 is
   monotonic) so the cursor is stable without a composite key.
4. Files and reminders return empty lists today — the paperless
   correspondent bridge and reminder→person tagging aren't shipped
   yet. Keep the endpoints wired so the frontend contract stays
   stable; delete the "empty branch" when the bridges land.

### Detach-face service (S13-003)
`api/services/face/detach_face_service.py::detach_face` is the
"this isn't them" primitive. Key differences from `split_person`:

- Creates a **new 1-member unconfirmed cluster** with
  `trusted_person_id=None`, not a new trusted_person. The face is
  "floating" until a future review pass reassigns it.
- Records `operation_type="detach_face"` in `person_operations`
  so it's undoable via `_apply_undo_detach_face` in
  `undo_service.py` (inverse: restore original cluster_id, then
  soft-delete the now-empty new cluster).
- Always calls `graph_edge_builder.build_person_photo_edges(...)`
  afterward because the face may have been the only link between
  the person and a given photo.

Migration 019 extends the `ck_person_operations_type` CHECK to
include `'detach_face'`. When adding new operation types, bump
the CHECK the same way.

### Graph edge query helpers (S13-008, S13-009)
Two query patterns repeat — factor into helpers if a third
appears:

1. **Person's denormalized sub-resources** (photos/events/files):
   join `GraphEdge` on `(from_type='trusted_person', from_id=:pid, to_type=..., edge_type=...)`
   then on the child table with workspace + soft-delete filters.
2. **Recent activity ranking** (Today feed, PersonCardSource):
   same join but grouped and counted, with a `taken_at >= cutoff`
   filter on the joined `PhotoAsset`. See
   `api/services/today/person_card_source.py::PersonCardSource.fetch`
   for the canonical shape — ORDER BY count DESC, LIMIT 3.

### Search includes trusted_persons (S13-009)
`api/services/query/search.py` grew a `"person"` type backed by
`search_trusted_persons` (ILIKE on `display_name`). It emits
`PersonCard`s with `payload.source="trusted_person"` so the web
client can disambiguate them from the pre-existing contact-based
person cards and route clicks to `/people/:id` instead of the
contact detail view. When adding new search types: extend the
`SearchType` literal, wire the branch in `search_all`, and
update the router's `type` query-param literal.

### PersonCardSource for Today (S13-009)
`api/services/today/person_card_source.py` is the first non-event
source added since Sprint 3. It fails closed on consent:
`await consent_service.is_consent_active(...)` returns False →
empty list, no exception. When consent is active it ranks persons
by recent (`taken_at >= now - 14d`) `appears_in` edge count and
emits up to 3 cards with `priority_score` descending from 0.68
(slots under calendar events in the default order). Add new
Today sources by following this shape: a class with a single
`fetch(today, now) -> list[Card]` method wired into
`assemble_today`.

### Photo lightbox endpoints (S13-008)
- `GET /api/v1/photos/{id}/full` — serves raw JPEG bytes from
  `file.path`. Non-JPEG mime types raise
  `PHOTO_UNSUPPORTED_FORMAT` (HEIC transcoding is deferred).
- `GET /api/v1/photos/{id}/faces` — left-joins
  `FaceDetection → FaceCluster → TrustedPerson` and returns
  normalized bbox + `trusted_person_display_name` +
  `trusted_person_avatar_url` per face. Always goes through the
  shared consent guard. The `_photo_to_card` helper is unchanged.

## Sprint 14 backend patterns (PLA Pack SDK)

### Pack manifest schema (S14-002)
`packs/<pack_id>/manifest.yaml` parsed by
`api/services/pack/manifest_loader.py`. Key fields:
`pack_id`, `capabilities` (list of `scope:target` strings from
`capability_registry.py`), `resource_limits`
(`max_execution_time_seconds`, `max_memory_mb`,
`max_llm_calls_per_run`), `card_types`, `schedule`
(`daily: "HH:MM"`, `weekly: "day HH:MM"`). All validated via
Pydantic field validators; unknown capabilities rejected at load.
`yaml.safe_load` only — never `yaml.load`.

### PackContext capability enforcement (S14-003)
Every public method on `PackContext` starts with
`self._require_capability(cap)`. Face-data methods additionally
call `self._require_face_consent()`. The factory strips
consent-gated capabilities when consent is off so the pack runs
with reduced data. `produce_card` validates card_type against the
manifest's declared set. `ask_llm` increments a quota counter
*before* the call (failures consume quota). All string outputs
are sanitized via `sanitizer.sanitize_text`.

### Pack card lifecycle (S14-004 → S14-009)
1. **Produce**: workflow calls `context.produce_card(card_type, payload)` → queued in context.
2. **Commit**: `PackRunner` writes `pack_cards` rows after successful run (target_date from trigger).
3. **Surface**: `PackCardSource` in Today assembly queries un-acknowledged, un-snoozed cards.
4. **Acknowledge**: `POST /api/v1/pack-cards/:id/acknowledge` stamps `acknowledged_at` + `acknowledged_action`. Snoozed cards carry `snoozed_until`.
5. **Dedup**: workflows check `has_pending_card_for_person` + `is_person_snoozed` before producing.

### Pack scheduler (S14-005)
Zero-dep asyncio cron loops — no APScheduler. Two tasks per pack
(daily + weekly). Each loop computes the next target time, sleeps,
fires for all workspaces that pass `pla_active`, then loops.
`health()` returns status for `/health`. Enable/disable via
`POST /admin/packs/:id/enable|disable` (toggles `_ENABLED_FLAGS`).

### Person-context query integration (S14-011)
`person_detector.py` extracts name spans → ILIKEs `trusted_persons`.
Four new deterministic intents: `person_who_is`, `person_files`,
`person_last_seen`, `person_photos`. In the LLM path (Step 1.5),
if a person is detected the context assembly switches from
`grounded_qa_v1` to `person_context_v1` so the model sees linked
events, files, and reminders alongside the question.
