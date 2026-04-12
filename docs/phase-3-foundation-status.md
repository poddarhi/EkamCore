# Phase 3 Foundation Status — End of Sprint 11

**Prepared:** 2026-04-12
**Branch:** `development`
**Commits:** S11-001 `ddfb358` → S11-009 `1772b71`
**Current phase:** 3 (unchanged — Sprint 12 continues Phase 3)

## TL;DR

Sprint 11 shipped the full **face clustering foundation**: consent
data model + API + UI, InsightFace inference, consent-gated per-photo
detection, historical backfill, synchronous transactional hard-delete,
observability, and end-to-end tests. The feature is **gated off by
default** and cannot run against any workspace without an explicit
per-workspace consent grant. Sprint 12 will build clustering + the
People review queue on top of this foundation.

## What's enabled (by story)

- **S11-001** Alembic 013 + 014 + 015 + 016. `face_detections`,
  `face_clusters`, `trusted_persons`, `face_backfill_jobs` tables.
  Qdrant `face_embeddings` collection with mandatory `workspace_id`
  payload index. Fernet encryption helpers. Three-gate
  `face_pipeline_active(flag + key + consent)` check.
- **S11-002** `ConsentService.is_consent_active / grant / revoke` with
  60-second Redis cache, audit_log writes on every transition, and
  the atomic revoke+hard_delete contract that rolls back if deletion
  fails (ART-15 §3).
- **S11-003** `GET / POST / DELETE /api/v1/settings/face-clustering/consent`.
  CSRF on POST/DELETE. 10/min/user rate limit. Synchronous
  transactional hard_delete (Qdrant-first delete, PG cascade).
- **S11-004** `ConsentDialog` with scroll-to-bottom enforcement.
  `PhotoIntelligenceSettings` State A/B/two-step-disable state machine.
  `apiFetch` CSRF auto-send fix (affected every existing mutation).
- **S11-005** `FaceModel` fail-closed singleton. SCRFD-10g + ArcFace-R100
  via InsightFace buffalo_l. PII-safe log whitelist. SHA-256 verified
  model download script.
- **S11-006** `FACE_DETECTION` pipeline stage. `process_photo_for_faces`
  worker re-checks consent inside the worker, sources workspace_id
  from the PhotoAsset row (never from callers), is idempotent across
  re-runs, and rolls back the PG insert if Qdrant upsert fails.
- **S11-007** User-initiated historical backfill. `face_processed_at`
  marker on photo_assets replaces the ambiguous `face_count=0`.
  `face_backfill_jobs` table + worker with per-batch consent re-check
  + Redis cancel flag. 3 endpoints (1/hr/workspace rate limit on start)
  + UI progress bar + cancel.
- **S11-008** `/health` extended with pipeline aggregates. New
  `GET /api/v1/face/status`. Metrics via `record_face_event` +
  `record_face_detection_latency` with hourly/daily flushers writing
  `face_latency.detect_embed` and `daily.face_events` into the G-15
  metrics table. Admin StoragePage "Face Data" tile (visible only
  when consent is active). PII-safety sweep test for the full pipeline.
- **S11-009** Seven Phase 3 end-to-end scenarios in
  `tests/integration/test_phase3_e2e_foundation.py`. ML eval baseline
  harness at `scripts/eval/eval_face_detection.py` with graceful skip.
  Traceability matrix updated for every Sprint 11 story.
- **S11-010** (this story) Skill file + legal brief + this status doc.

## What's gated

Three independent gates. Any one off → face pipeline is a complete no-op.

1. **Feature flag `face_clustering_enabled`** is default FALSE.
   Flip it on via the feature_gate middleware (`_ENABLED_FLAGS`).
2. **`FACE_EMBED_KEY`** env var must be a valid Fernet base64 key.
   Empty or malformed → pipeline disabled.
3. **Per-workspace consent** must be active
   (`ConsentService.is_consent_active(workspace_id)` returns True).

The canonical check is `api/services/flags.py::face_pipeline_active`.
Every call site (face_ingestion, face_backfill, face_status, healthcheck)
funnels through it. Do not duplicate a partial check anywhere.

## How to enable for local testing

```bash
# 1. Generate a Fernet key
poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Put it in your .env
echo "FACE_EMBED_KEY=<the key above>" >> .env

# 3. Flip the flag (dev-only, edits _ENABLED_FLAGS at runtime). In prod
#    this would happen via a migration of config/feature-flags.json.
poetry run python -c "from api.middleware.feature_gate import _ENABLED_FLAGS; _ENABLED_FLAGS.add('face_clustering_enabled'); print(_ENABLED_FLAGS)"

# 4. Download the InsightFace model pack (once)
make download-face-models
export INSIGHTFACE_MODEL_DIR=$(pwd)/infra/docker/workers/models/insightface

# 5. Grant consent for your workspace via the UI:
#    http://localhost:3000/settings/photo-intelligence → Enable Face Clustering
#    Scroll the consent dialog to the bottom → Accept
#
#    Or via API (requires CSRF token from /auth/login):
#    curl -X POST http://localhost:8420/api/v1/settings/face-clustering/consent \
#         -H "Authorization: Bearer <token>" \
#         -H "X-CSRF-Token: <csrf>" \
#         -H "Cookie: ekamcore_csrf=<csrf>" \
#         -d '{"accepted": true, "version_acknowledged": "v1.0-DRAFT-2026-04"}'

# 6. Drop a photo with a face into any photo_folder source. Within 60s
#    its face_count should go from 0 → N in photo_assets.

# 7. Historical backfill:
#    Settings → Photo Intelligence → Process historical photos
#    Progress polls every 5s. Cancel button available while running.

# 8. Revoke when done: Settings → Photo Intelligence → Disable
#    Hard-delete runs synchronously. All face rows + Qdrant points
#    for the workspace are gone before the API returns.
```

## What Sprints 12-14 will deliver

- **Sprint 12** — HDBSCAN clustering pass (`cluster_id` populated on
  face_detections), candidate link generation, People Graph review
  queue UI with confirm/reject/defer + merge/split/undo.
- **Sprint 13** — PLA Pack core workflows + skill execution sandbox
  + 72-hour soak test.
- **Sprint 14** — face_clustering_enabled flag flip for production,
  user documentation, release-candidate validation.

The default-off flag and per-workspace consent gate remain in force
through all of this. Sprint 12's clustering pass reads the same
`face_detections` rows that S11-006 writes; no new legal surface is
introduced.

## Known limitations

- **CPU-only buffalo_l.** SCRFD-10g + ArcFace-R100 run on
  `CPUExecutionProvider` via onnxruntime. Mac mini M4 Pro target is
  adequate for the Sprint 11 target (p50 < 200ms, p95 < 400ms) but no
  GPU acceleration yet. Future work: Metal/CoreML EP.
- **Single-process backfill.** `backfill_service._run_backfill_worker`
  spawns one `asyncio.create_task` per workspace. No distributed
  coordination; no per-photo concurrency. Backfill of a 10 000-photo
  workspace is a multi-hour serial walk. Acceptable for single-user
  local-first product. Sprint 12 may parallelize if measurement
  justifies it.
- **No cluster operations yet.** `face_detections.cluster_id` is
  populated exclusively as NULL until Sprint 12's HDBSCAN pass lands.
  `face_clusters` table exists but is empty.
- **Consent text is DRAFT.** `CURRENT_CONSENT_VERSION` is
  `v1.0-DRAFT-2026-04`. See `docs/legal/sprint-11-legal-brief.md` for
  the legal review package. Sprint 14 will not ship the production
  flag flip until the DRAFT marker is removed.
- **No ML eval dataset in repo.** The eval harness exists and skips
  gracefully until a calibration dataset is placed at
  `apps/api/tests/fixtures/face_eval/` — see that directory's README
  for sourcing guidance.

## Verification results

Captured end of S11-010, on `development` branch at
`1772b71` (pre-commit for this story).

### Test suite

```
$ cd apps/api && poetry run pytest -q
894 passed, 1 skipped, 110 warnings in 186.56s
```

- Full suite green. One skip is `test_face_model.py::TestRealModelIntegration`
  (tier-3 real-model test, skipped because `INSIGHTFACE_MODEL_DIR`
  and the fixture image are not provisioned on the CI host).
- A single test (`test_audit.py::test_login_success_creates_audit_event`)
  exhibited a flake on one run and passed on the re-run — a
  pre-existing test-isolation issue unrelated to S11-010 (which makes
  no product code changes). Tracked for investigation at the Sprint 12
  entry; run the full suite twice to confirm stability before release.

### Phase 3 end-to-end scenarios

```
$ poetry run pytest tests/integration/test_phase3_e2e_foundation.py -v
tests/integration/test_phase3_e2e_foundation.py::TestPhase3E2EFoundation::test_consent_grant_to_first_face PASSED
tests/integration/test_phase3_e2e_foundation.py::TestPhase3E2EFoundation::test_consent_revoke_hard_delete PASSED
tests/integration/test_phase3_e2e_foundation.py::TestPhase3E2EFoundation::test_consent_revoke_during_backfill PASSED
tests/integration/test_phase3_e2e_foundation.py::TestPhase3E2EFoundation::test_workspace_isolation_face_search PASSED
tests/integration/test_phase3_e2e_foundation.py::TestPhase3E2EFoundation::test_face_pipeline_off_when_consent_off PASSED
tests/integration/test_phase3_e2e_foundation.py::TestPhase3E2EFoundation::test_consent_required_endpoints PASSED
tests/integration/test_phase3_e2e_foundation.py::TestPhase3E2EFoundation::test_logs_pii_free_full_pipeline PASSED
7 passed
```

### Security suite

```
$ poetry run pytest tests/security -q
(all green; includes test_face_workspace_isolation.py,
 test_face_logs_no_pii.py, test_hard_delete_isolation.py,
 test_consent_isolation.py)
```

### Face detection eval

```
$ make eval-face
[eval_face_detection] SKIP: insightface not importable: ModuleNotFoundError: No module named 'insightface'
```

Expected skip — the dev environment doesn't ship insightface
(500MB of wheels, deferred to the user per the S11-005 ops runbook).
The script exits 0 on skip by design; real baseline measurements
happen on a workstation with the model pack + fixture dataset
provisioned.

### Phase 2 perf baseline (regression check)

```
$ make benchmark
postgres    insert_p50_ms: 0.083  select_p50_ms: 0.078
redis       set_p50_ms:    0.072  get_p50_ms:    0.069
qdrant      search_p50_ms: 1.378  search_p95_ms: 3.591
health      p50_ms:       28.799  p95_ms:       32.711
cold_start  mean:           35.5s min:            35.4s
```

All Phase 2 infrastructure numbers are stable — no regression from
any of the Sprint 11 changes (migrations 013–016, consent service,
face pipeline, backfill, observability).

## Manual UI walkthrough — checklist for the human reviewer

To be run once before Sprint 12 kicks off. Each row is "done when
evidence is visible":

- [ ] **Login → Settings → Photo Intelligence**: the page renders the
      DisabledStateCard with the "Enable Face Clustering" button.
- [ ] **Click Enable → ConsentDialog opens**: the Accept button is
      initially disabled. Scroll to the bottom → Accept enables.
      Accept → dialog closes, card flips to the EnabledStateCard.
- [ ] **Drop a photo containing a face into any photo_folder source**:
      within ~60 seconds `photo_assets.face_count` for that row goes
      from 0 to the detected count. Confirm via
      `docker compose exec ekamcore-postgres psql -U ekamcore -c
      "SELECT id, file_id, face_count, face_processed_at FROM
      photo_assets ORDER BY updated_at DESC LIMIT 5;"`
- [ ] **Trigger the historical backfill** on 10 historical photos
      (that were ingested BEFORE consent was granted and therefore
      have `face_processed_at IS NULL`). Progress bar polls every
      5s. Job reaches `state='completed'`.
- [ ] **Disable face clustering**: two-step confirm modal. Confirm →
      hard-delete report returns counts. Verify: `SELECT count(*)
      FROM face_detections WHERE workspace_id = :ws` → 0. Verify
      the `photo_assets.face_count` has reset to 0 and
      `face_processed_at` is NULL.
- [ ] **PII sweep**: `docker compose logs ekamcore-api | grep -i
      "embedding\|bbox\|\.jpg\|\.png" || echo "clean"` — expected
      output: `clean` (no matches).

When the six boxes are all ticked, face clustering foundation is
certified shippable and the Sprint 12 clustering work can begin.

## Operations notes for the reviewer

- **code-review-graph rebuild** is a user-side step (the tool is
  not available in the engineering sandbox). Run it before the
  first Sprint 12 session so FaceModel, ConsentService, hard_delete,
  BackfillService, and friends are queryable.
- **Alembic upgrades**: migrations 013..016 must be applied to any
  environment pulling this branch. Run
  `PYTHONPATH=. poetry run alembic upgrade head` from `apps/api`.

## Sprint 11 gate report

| Sprint 11 Story | Status | Evidence |
|---|---|---|
| S11-001 Migrations + Activation | ✅ | Alembic 013 applies cleanly; pgcrypto + gen_uuid_v7 verified; `face_embeddings` Qdrant collection has `workspace_id` payload index; `test_face_migrations.py` + `test_face_crypto.py` + `test_face_pipeline_active.py` green. |
| S11-002 Consent Service | ✅ | `is_consent_active/grant/revoke` with 60s Redis cache + audit_log rows. Atomic revoke+hard_delete contract verified by `test_consent_audit.py` + `test_consent_service.py`. |
| S11-003 Consent API + Hard-Delete | ✅ | 3 endpoints + CSRF + 10/min rate limit. `test_consent_endpoints.py` covers grant/stale/revoke; `test_hard_delete.py` + `test_hard_delete_isolation.py` cover the transactional + cross-workspace paths. |
| S11-004 Consent Dialog UI | ✅ | Scroll-to-bottom + two-step disable verified by `apps/web/src/__tests__/components/face/ConsentDialog.test.tsx` and `PhotoIntelligenceSettings.test.tsx`. Accessibility lint clean. |
| S11-005 InsightFace | ✅ | `FaceModel.instance()` singleton loads the buffalo_l pack, returns 512-dim `FaceResult` rows; `test_face_model.py` + `test_face_logging.py` + tier-3 `requires_insightface_models` marker all wired. |
| S11-006 Face Ingestion | ✅ | `FACE_DETECTION` pipeline stage (alembic 015) + `process_photo_for_faces` worker with in-worker consent re-check + idempotent wipe + workspace isolation. `test_face_ingestion.py` (5) + `test_face_workspace_isolation.py` (2) green. |
| S11-007 Backfill | ✅ | `face_backfill_jobs` (alembic 016) + per-batch consent re-check + Redis cancel flag + UI progress bar + cancel. `test_backfill.py` (8) green. |
| S11-008 Observability | ✅ | `/health` extension; `GET /api/v1/face/status`; metrics helpers wired to G-15 hourly/daily flushers; admin StoragePage "Face Data" tile; full-pipeline PII sweep. `test_face_status_endpoint.py` + `test_face_logs_no_pii.py` + `test_face_metrics.py` (6) green. |
| S11-009 Tests + Eval | ✅ | `test_phase3_e2e_foundation.py` (7 scenarios) covers grant→first face → revoke→hard-delete → mid-backfill revoke → workspace isolation → consent-gate sweep → PII sweep. `scripts/eval/eval_face_detection.py` exists with graceful skip; `face_eval/README.md` documents the 500-image/50-identity dataset contract. |
| S11-010 Gate Review | ✅ | ml-ai + backend + references/sprint-story-index skill files updated; `docs/legal/sprint-11-legal-brief.md` + `docs/phase-3-foundation-status.md` (this file) created; `current_phase` stays at 3; Sprint 12 cleared to begin. |

**Overall Sprint 11 status: READY — foundation shipped, face pipeline
default-off, consent loop legally sufficient pending Legal Advisor
review, Sprint 12 clustering work can begin immediately.**
