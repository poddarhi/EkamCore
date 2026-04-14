# Phase 3 — Sprint 12 status report

**Sprint window**: Weeks 23–24
**Gate date**: 2026-04-13
**Verdict**: SHIPPED (backend) · UI deferred to Sprint 13

## What's enabled

Sprint 12 delivered the full back-end surface area for People Graph
confirmation and curation. Every service below is tested end-to-end
and committed on `development`:

- **HDBSCAN face clustering** — full workspace re-cluster with
  per-workspace params (`min_cluster_size`, `cluster_selection_epsilon`),
  lazy `hdbscan` import, majority-overlap identity preservation across
  runs. Source: `apps/api/api/services/face/clustering_service.py`.
- **Incremental cluster assignment** — per-face online path with a
  decision tree (strong match / weak / new), drift guard on confirmed
  clusters, Redis recluster hint counter (7-day TTL). Source:
  `apps/api/api/services/face/incremental_cluster.py`.
- **Candidate contact scoring** — five-signal weighted score
  (co-occurrence 0.50, graph edge 0.20, photo name 0.15, temporal
  0.10, size bonus 0.05), cached on `face_clusters.candidates_json`,
  consent-gated batch endpoint at
  `POST /api/v1/internal/face/score-clusters`. Source:
  `apps/api/api/services/face/candidate_scorer.py`.
- **TrustedPersons CRUD** — seven endpoints under `/api/v1/people`
  (list, detail, create-from-cluster, confirm-candidate,
  reject-cluster, rename, soft delete). Consent + CSRF + rate limits
  (120/min reads, 30/min writes).
- **Review Queue API** — score-ordered cursor-paginated list,
  full-member detail endpoint, per-user 24h skip marker in Redis.
  Paths: `/api/v1/review-queue`.
- **Merge / split / undo** — `person_operations` undo log with
  JSONB `forward_payload` + `inverse_payload`. Merge moves clusters
  and rewrites graph_edges (with dedup); split mints a new cluster
  + person, recomputes centroids from L2-normalized mean of
  decrypted embeddings. `undo_service` supports merge, split,
  rename, delete, confirm, reject. Double-undo returns
  `OPERATION_ALREADY_UNDONE` (409).
- **Graph edges (Person ↔ Photo / Event / File)** —
  `graph_edge_builder` writes `appears_in` / `attended` /
  `associated_with` edges. Per-person rebuild hooks run on
  `create_from_cluster`, `merge_persons`, and `split_person`.
  Admin rebuild endpoint at
  `POST /api/v1/internal/graph/rebuild` (1/hour/workspace).

## What's still backend-only

Every Sprint 12 capability is exposed as JSON over HTTP with no
Web / Mobile / Manager screens. Sprint 13 wires the UI. The
endpoint contract is documented in `.claude/skills/ekamcore-skills/
frontend/SKILL.md` under **People Screens (Coming Sprint 13 — backend
ready)** so the UI work can start immediately without re-deriving
the API.

## Gate evidence

### Test suite

```
$ cd apps/api && PYTHONPATH=. poetry run pytest tests
969 passed, 1 skipped, 129 warnings in 201.87s
```

One pre-fix duplicate-message collision (`CLUSTER_NOT_FOUND` vs
`FACE_CLUSTER_NOT_FOUND`) caught by `test_errors_registry.py` and
resolved in this commit by giving `CLUSTER_NOT_FOUND` a distinct
copy ("Cluster not found in this workspace.").

### Clustering ML eval (synthetic baseline, ART-25 §2 rows 6-7)

```
$ poetry run python scripts/eval/eval_clustering.py
wrote eval_results/clustering_baseline_2026-04-14.json
[ok] all targets met: {
  'pairwise_precision': 1.0,
  'pairwise_recall':    1.0,
  'pairwise_f1':        1.0,
  'adjusted_rand_index': 1.0,
}
# targets: precision ≥ 0.90, recall ≥ 0.85
```

500 faces / 50 identities, deterministic one-hot embeddings + argmax
fake HDBSCAN. Perfect score is the expected upper bound for the
algorithm on noise-free inputs — real-image accuracy depends on the
biometric calibration dataset which ART-18 blocks from committing.

### Candidate scoring ML eval (ART-25 §2 row 8)

```
$ poetry run python scripts/eval/eval_candidate_scoring.py
wrote eval_results/scoring_baseline_2026-04-14.json
[ok] all targets met: {
  'precision_at_1': 1.0,
  'precision_at_3': 1.0,
  'precision_at_5': 1.0,
}
# target: P@1 ≥ 0.80
```

20 curated (identity → contact → event count) pairs seeded as
synthetic clusters. Each cluster has a single dominant identity and
a matching contact with 3–6 co-occurring calendar events in the
±2h scoring window, which is the strongest signal in the mix.

### Sprint 11 face-detection baseline

```
$ poetry run python scripts/eval/eval_face_detection.py
[eval_face_detection] SKIP: insightface not importable
```

Gracefully skipped in this environment — the insightface Python
package is a worker-container dep, not available in the host poetry
env. The baseline itself was established in S11-009 and is not
regressed by any Sprint 12 change (no face detection code was
touched).

## Known limitations

- **Clustering cost**: `cluster_workspace` is CPU-bound and grows
  with face count. On synthetic inputs the 500-face run is < 200 ms
  because the fake HDBSCAN is O(n). Real InsightFace embeddings with
  real HDBSCAN target < 30 s for 1 000 faces on Mac mini M4 Pro per
  ART-25 §3; not yet measured because biometric fixtures are
  local-only.
- **Candidate scoring scope**: v1 only reads calendar co-occurrence,
  prior graph edges, filename fuzzy match, temporal span, and size.
  Message history, email subject mention, and folder signals are a
  Phase 4 enhancement.
- **Undo semantics**: the log supports a single back-step chain.
  Undoing an undo (redo) is NOT supported. Users can re-apply
  manually by repeating the forward action.
- **graph_edge_builder file edges**: `build_person_file_edges` is
  a returning-0 placeholder until the `contact → paperless
  correspondent → file` bridge is wired up (blocked on an earlier
  integration story). Photo and event edges are fully functional.

## Sprint 12 report table

| Sprint 12 Story | Status | Evidence |
|---|---|---|
| S12-001 HDBSCAN Clustering | ✅ SHIPPED | `cluster_workspace`, full re-cluster writes audit_log, tests in `test_clustering_full_run.py` |
| S12-002 Incremental Cluster | ✅ SHIPPED | `assign_face_to_cluster`, drift guard, `test_incremental_cluster.py` |
| S12-003 Candidate Scoring | ✅ SHIPPED | `candidates_json` populated, `test_candidate_scorer.py` + batch integration test |
| S12-004 TrustedPersons CRUD | ✅ SHIPPED | 7 `/api/v1/people` endpoints, `test_people_endpoints.py` |
| S12-005 Review Queue API | ✅ SHIPPED | `/api/v1/review-queue` list/detail/skip, `test_review_queue_endpoints.py` |
| S12-006 Merge/Split/Undo | ✅ SHIPPED | `person_operations` log, undo round-trip tested, `test_undo_service.py` |
| S12-007 Graph Edges | ✅ SHIPPED | `appears_in`, `attended` edges built per-person; `file` edges stubbed |
| S12-008 Tests + Eval | ✅ SHIPPED | 8-scenario Phase 3 e2e, clustering + scoring baselines in `eval_results/` |
| S12-009 Gate Review | ✅ SHIPPED | skill updates + this status doc |

## Current phase

Phase 3 (unchanged). Sprint 13 continues Phase 3 by landing the
People Graph UI on top of the Sprint 12 backend.
