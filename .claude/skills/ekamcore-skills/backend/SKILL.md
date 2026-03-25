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
Stages: DISCOVERED → FINGERPRINTED → METADATA_EXTRACTED → TEXT_EXTRACTED → OCR_COMPLETED → EMBEDDING_QUEUED → EMBEDDED → COMPLETED. Also: FAILED, SKIPPED.
Transition: UPDATE ingestion_states SET current_stage=:new WHERE file_id=:fid AND current_stage=:expected. If 0 rows: already advanced (idempotent).
Per-file error isolation: one file's failure never blocks another.

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
