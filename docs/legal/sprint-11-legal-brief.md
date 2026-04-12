# Sprint 11 Legal Review Brief — Face Clustering Foundation

**Status:** DRAFT — awaiting Legal Advisor review
**Prepared:** 2026-04-12 (end of Sprint 11)
**Owner:** EkamCore engineering
**Audience:** Project Legal Advisor

---

## Cover note — what Sprint 11 built, and what it does NOT yet do

Sprint 11 built the **foundation** of the EkamCore face clustering
feature. Nine stories (S11-001 through S11-009) landed the full
consent-granting loop, the ML inference layer, the per-workspace
hard-delete guarantee, a user-initiated historical backfill, and the
observability surface around all of it. The feature is gated behind
a default-off flag and cannot run against any workspace without
explicit per-workspace consent.

### What ships in this sprint
- Biometric consent data model, grant/revoke service, audit trail
- `GET / POST / DELETE /api/v1/settings/face-clustering/consent`
- `ConsentDialog` UI with scroll-to-bottom enforcement, two-step
  disable confirmation
- InsightFace SCRFD-10g (detector) + ArcFace-R100 (recognizer),
  running locally on CPU, reading models from the workers container
  at `/models/insightface`
- Per-photo face detection stage wired into the photo ingestion
  pipeline, gated on active consent
- User-initiated historical photo backfill with live progress + cancel
- Synchronous, transactional hard-delete on consent revocation
  (Qdrant-first delete, PG cascade, audit row) — ART-15 §3
- `/health`, `/api/v1/face/status`, and admin storage dashboard tile
- 7 Phase 3 end-to-end integration scenarios + the face detection ML
  eval baseline harness (`scripts/eval/eval_face_detection.py`)
- 894 backend tests passing, 1 skipped, 0 failing

### What Sprint 11 deliberately does NOT yet do
- **No face clustering.** The HDBSCAN clustering pass is Sprint 12.
  Detected faces sit in `face_detections` with `cluster_id = NULL`
  until then.
- **No "People" UI.** The review queue where the user labels clusters
  with names is also Sprint 12.
- **No face search.** There is no end-user query path that takes a
  face image and returns matches; the embeddings exist but nothing
  consumes them for retrieval yet.
- **No end-user availability.** `face_clustering_enabled` flag is
  default false. Even if it were flipped on, no workspace will
  actually run face detection until the user grants consent.
- **Consent text is DRAFT.** The DRAFT marker on the current text
  remains until this review concludes.

### Why we are asking for review now
We are asking for review at the foundation stage specifically so
that any edits the Legal Advisor requests land **before** any real
user's consent is stored against the current text. If the reviewer
recommends changes after Sprint 14 (when the feature ships), we
will have to re-prompt users and bump `CURRENT_CONSENT_VERSION`
anyway — but more users will be inconvenienced.

---

## 1. Full current consent text

Source of truth: `apps/api/api/services/face/consent_text.py`

> **Version:** `v1.0-DRAFT-2026-04`

```
FACE CLUSTERING — BIOMETRIC DATA CONSENT (DRAFT)

This screen requests your explicit, informed consent for EkamCore to
detect and cluster faces found in your photo library. Please read the
entire notice before choosing to enable this feature.

1. WHAT DATA IS COLLECTED
   If you enable face clustering, EkamCore will:
     • Scan each image in your photo library for faces.
     • Record a rectangle (bounding box) locating each detected face.
     • Compute a 512-dimensional numerical fingerprint of each face —
       a face embedding — using a local neural network (ArcFace).
     • Group embeddings that appear to belong to the same person so
       you can label clusters with names you choose.

   Face embeddings are biometric identifiers. They are treated as
   biometric data under the Illinois Biometric Information Privacy
   Act (BIPA), the EU General Data Protection Regulation (GDPR),
   and the California Consumer Privacy Act / California Privacy
   Rights Act (CCPA / CPRA).

2. WHERE IT IS STORED
   All face data stays on your Mac. Specifically:
     • Detection metadata (bounding boxes, detector version) lives
       in the local PostgreSQL database inside the EkamCore Docker
       stack on your machine.
     • Face embeddings are encrypted at rest with an application-
       side symmetric key before being written to disk. Both the
       PostgreSQL bytea column and the Qdrant vector store receive
       encrypted representations. The decryption key lives only in
       the EkamCore API process memory.
     • No face data, no embeddings, and no detection metadata are
       ever transmitted off your machine. There is no cloud
       backend. There is no telemetry. There are no third-party
       analytics. There are no external AI providers.

3. HOW TO DELETE YOUR DATA
   You can revoke consent at any time:
     Settings → Photo Intelligence → Disable Face Clustering

   Revocation is immediate and complete:
     • All face_detection rows for your workspace are hard-deleted.
     • All face_cluster rows for your workspace are hard-deleted.
     • All Qdrant face_embedding points for your workspace are
       removed from the vector store.
     • The encryption key is not retained separately — revocation
       leaves no recoverable ciphertext behind.

   The revocation event itself is recorded in the append-only
   audit log (see §6) so that you have proof of the deletion.

4. RETENTION
   Face data is retained ONLY while your consent is active. When
   you revoke consent, deletion happens synchronously before the
   revocation is confirmed. If the deletion fails for any reason,
   the revocation is rolled back and you will be asked to retry.

5. NO AUTO-EXPIRATION
   Your consent does NOT expire automatically based on time. It
   remains in force until (a) you revoke it, or (b) the consent
   text on this screen changes in a way that requires fresh
   acknowledgement (we bump the version number and re-prompt).

6. LEGAL BASIS AND RIGHTS
   Under BIPA, GDPR, and CCPA / CPRA, you have the right to:
     • Be informed about what biometric data is collected
       (§1 above).
     • Refuse consent without losing access to the rest of
       EkamCore — face clustering is strictly optional.
     • Withdraw consent at any time (§3 above).
     • Request deletion of any biometric data — which, under
       EkamCore's local-first architecture, is accomplished by
       revoking consent.

   Every grant and every revocation of face clustering consent
   is recorded in the append-only audit log on your machine,
   along with the timestamp, your user ID, your IP address, the
   user agent string of the client that performed the action,
   and the exact version of this consent text that you accepted.

7. NO THIRD PARTIES
   Face data is never shared with any third party. There are no
   data processors, data controllers, or joint controllers other
   than EkamCore running locally on your Mac, which is operated
   by you. You are the data subject AND the data controller.
```

---

## 2. Relevant spec excerpts

### ART-14 §9 — Encryption at rest (extract)

> Face embeddings are biometric identifiers and MUST be encrypted
> at rest with an application-side symmetric key. Storage in both
> Postgres (bytea) and Qdrant (payload or vector) MUST contain
> only ciphertext. The encryption key lives in process memory and
> is configured via the `FACE_EMBED_KEY` environment variable. An
> empty or invalid key SHALL disable the face pipeline at the
> `face_pipeline_active` gate (see §11).

### ART-14 §11 — Workspace isolation (extract)

> Every query that reads or writes biometric data MUST be scoped
> to a single `workspace_id`. Qdrant filters MUST include a
> `workspace_id` clause; PG queries MUST include a `workspace_id`
> predicate. The `workspace_id` value MUST be sourced from the
> server-side row being acted on (e.g. `photo_asset.workspace_id`)
> or from the authenticated user's session, NEVER from a client-
> supplied query parameter. This is the primary control for the
> "confused deputy" class of failure.

### ART-15 §3 — Compliance checklist (referenced, not reproduced)

Full text lives at `docs/specs/ART-15.md`. The applicable rows
are transcribed in the compliance matrix below.

---

## 3. Compliance matrix (ART-15 §3)

| Requirement | Sprint 11 implementation | Code reference | Test reference |
|---|---|---|---|
| **Explicit informed consent** before any biometric processing | `ConsentDialog` requires scroll-to-bottom before Accept enables. The current `CURRENT_CONSENT_VERSION` string is stored with every grant so a later re-prompt is unambiguous. | `apps/web/src/components/face/ConsentDialog.tsx`, `apps/api/api/services/face/consent_service.py::grant` | `tests/integration/test_consent_endpoints.py::TestPostConsent`, `apps/web/src/__tests__/components/face/ConsentDialog.test.tsx` |
| **Right to refuse** without loss of access | Face clustering is strictly optional. All non-face EkamCore features (today, search, query, recap, calendars) work identically regardless of consent state. The three-gate `face_pipeline_active` check is the ONLY enforcement surface. | `apps/api/api/services/flags.py::face_pipeline_active` | `apps/api/tests/test_face_pipeline_active.py` |
| **Right to withdraw at any time** | `DELETE /api/v1/settings/face-clustering/consent` runs synchronously from a single user click. The `PhotoIntelligenceSettings` UI surfaces a two-step confirm; a one-click revoke is never possible, but it's also never more than two clicks away. | `apps/api/api/routers/face_consent.py::delete_consent`, `apps/web/src/pages/settings/PhotoIntelligenceSettings.tsx` | `tests/integration/test_consent_endpoints.py::TestDeleteConsent` |
| **Right to deletion — synchronous, verified** | Revocation hard-deletes in one atomic transaction: Qdrant delete-by-filter first (ART-15 §3 row: over-deletion LEGAL, under-deletion ILLEGAL), verify Qdrant count = 0, then PG cascade (face_detections → face_clusters → photo_assets.face_count/face_processed_at reset). Any failure propagates and rolls the revocation back. | `apps/api/api/services/face/hard_delete.py::delete_all_face_data` | `apps/api/tests/test_hard_delete.py`, `apps/api/tests/security/test_hard_delete_isolation.py`, `tests/integration/test_phase3_e2e_foundation.py::test_consent_revoke_hard_delete` |
| **Encryption at rest** for biometric identifiers | Embeddings are Fernet-encrypted (AES-128-CBC + HMAC-SHA256) with `FACE_EMBED_KEY` before being written to Postgres `bytea` or Qdrant. Missing / malformed key disables the pipeline at the three-gate check. | `apps/api/api/services/face/crypto.py` | `apps/api/tests/test_face_crypto.py` |
| **Workspace isolation** as the primary control | Every face query is per-workspace. Qdrant `face_embeddings` collection has a mandatory `workspace_id` payload index. The three-gate check is workspace-scoped. `process_photo_for_faces` sources `workspace_id` from `photo_asset.workspace_id` (defense in depth against spoofing). | `apps/api/api/services/qdrant_init.py`, `apps/api/api/services/face/face_ingestion.py` | `apps/api/tests/security/test_face_workspace_isolation.py`, `tests/integration/test_phase3_e2e_foundation.py::test_workspace_isolation_face_search` |
| **Append-only audit trail** of grants + revocations | Every grant / revoke / hard-delete emits an `object_audit_log` row with `action`, `user_id`, `workspace_id`, `ip`, `user_agent`, and the exact consent version string. The three rows land in strict order: `face_consent_granted` → `face_data_hard_deleted` → `face_consent_revoked`. | `apps/api/api/services/audit.py`, `apps/api/api/services/face/consent_service.py` | `apps/api/tests/test_consent_audit.py`, `tests/integration/test_phase3_e2e_foundation.py::test_consent_revoke_hard_delete` |
| **PII-safe logging** (biometric data never logged) | Every face pipeline log event passes through a whitelist of allowed field names (workspace_id, photo_asset_id, counts, timings, version strings, error types). The sweep test captures every event emitted during a full grant+detect+revoke cycle and asserts zero bbox dicts, zero numeric lists, zero filename substrings. | `apps/api/api/services/face/` (all modules) | `apps/api/tests/test_face_logging.py`, `apps/api/tests/security/test_face_logs_no_pii.py`, `tests/integration/test_phase3_e2e_foundation.py::test_logs_pii_free_full_pipeline` |
| **No third-party transmission** | EkamCore is local-first. The workers container has no outbound connectivity to any AI provider, analytics endpoint, or cloud backend for face data. There is no telemetry channel for biometric data; the only metrics recorded are counts and timings, locally, in the same database that stores the biometric data itself. | Supply-chain audit (G-12) confirms no outbound face data paths. | `scripts/sbom/license_audit.sh`, `tests/integration/test_phase2_e2e.py::test_no_outbound_telemetry` |

---

## 4. Direct ask for the Legal Advisor

> **Please review the consent text in §1 for legal sufficiency
> under BIPA, GDPR, and CCPA/CPRA. Edits become a one-line patch
> to `apps/api/api/services/face/consent_text.py`. We will bump
> `CURRENT_CONSENT_VERSION` on your edits, and any user whose
> stored consent version is now stale will be forced to re-consent
> before the face pipeline resumes for their workspace.**

Specific points we would welcome feedback on:

1. Is the §1 disclosure of "what data is collected" specific
   enough under BIPA's written-release requirement?
2. Does the §3 deletion wording satisfy GDPR Article 17 ("right
   to erasure") given that the deletion is synchronous and
   verified on revocation?
3. Is the CCPA/CPRA "right to know / right to delete" coverage
   complete, or should we add explicit language about the local-
   first architecture meaning the user is both data subject AND
   data controller (§7)?
4. Does the §6 retention-of-audit-metadata (timestamp, IP, UA,
   version) raise any privacy concerns under GDPR Article 5 data
   minimization? Note: the audit row is retained even after
   biometric data deletion so that we can prove the deletion
   happened.
5. Any jurisdiction-specific risks we are missing — TDPSA, CDPA,
   UCPA, state BIPA analogues.

---

## 5. Turnaround and parallelism

- **Estimated turnaround:** 2 weeks from receipt of this brief.
- **Parallel work:** Sprint 12 (HDBSCAN clustering + People review
  queue) begins immediately and proceeds independently. Clustering
  consumes the same face_detections table and workspace_id payloads
  — no legal risk is added by Sprint 12, because the same consent
  gate remains in effect.
- **Rewrite contingency:** If the reviewer requests a substantive
  rewrite, we bump `CURRENT_CONSENT_VERSION`, force re-consent at
  the next session for every user with a stale record, and land
  the rewrite as a single-file patch. Sprint 12 is not blocked.
- **Ship contingency:** If the reviewer asks us to hold the
  `face_clustering_enabled` flag off until a specific legal
  milestone, we will hold it off. The flag is default false today
  and requires an explicit toggle to enable.

---

## 6. How to give feedback

- **Preferred:** PR against `apps/api/api/services/face/consent_text.py`
  with the edits inline, so we can bump the version and merge in one
  go. Leave review comments on the PR.
- **Alternative:** Markdown redline of §1 above, sent to the engineering
  lead. We'll open the PR for you.

The consent text string is the ONLY file whose content matters for
the legal review. Every supporting artifact (schema, service, audit,
tests) has already been shaped to satisfy ART-15 §3. The gating
question is whether the *words* the user reads are legally
sufficient.
