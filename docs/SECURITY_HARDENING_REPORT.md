# Security Hardening Report (S15-010 / ART-14 §19)

**Date:** 2026-04-16
**Phase:** 4 (Sprint 15)
**Automated checklist:** `scripts/security/pen_test_checklist.py`

## Overview

This report documents the security posture of EkamCore against the ART-14 §19
hardening checklist. All automated checks are run via the pen test checklist
script; items requiring manual testing are noted.

## Checklist Results

### A. TLS Verification

| Check | Status | Notes |
|-------|--------|-------|
| HTTPS endpoint reachable | PASS | Caddy auto-provisions TLS certificate |
| Reject TLS 1.0 / 1.1 | PASS | Caddy defaults to TLS 1.2+ |
| Certificate present | PASS | Self-signed for localhost (Caddy auto-HTTPS) |
| Certificate auto-renewed | PASS | Caddy handles renewal automatically |

### B. Authentication

| Check | Status | Notes |
|-------|--------|-------|
| Missing auth → 401/403 | PASS | All protected endpoints return 401 without token |
| Invalid token → 401 | PASS | Arbitrary strings rejected |
| Tampered JWT → 401 | PASS | Signature verification catches modification |
| Expired JWT → 401 | PASS | Token expiry enforced |
| Valid token accepted | PASS | Standard auth flow works |
| Health/login no auth needed | PASS | Public endpoints accessible |

### C. Authorization

| Check | Status | Notes |
|-------|--------|-------|
| Admin endpoints require auth | PASS | `/api/v1/admin/*` returns 401/403 without token |
| Workspace isolation (2 users) | **MANUAL** | Requires 2 test users in different workspaces |

### D. Input Validation

| Check | Status | Notes |
|-------|--------|-------|
| SQL injection blocked | PASS | Parameterized queries via SQLAlchemy ORM (Golden Rule #2) |
| XSS escaped | PASS | JSON API — no HTML rendering of user input |
| Oversized body rejected | PASS | 413 or handled gracefully |
| Path traversal blocked | PASS | Returns 404 for `../../etc/passwd` |

### E. Rate Limiting

| Check | Status | Notes |
|-------|--------|-------|
| Auth rate limiting (10/min) | PASS | 429 returned after threshold |
| General rate limiting | PASS | Resource controller manages concurrent access |

### F. Secrets Hygiene

| Check | Status | Notes |
|-------|--------|-------|
| No hardcoded secrets in compose | PASS | All secrets via env vars or Keychain |
| .env not in git | PASS | Listed in .gitignore |
| No secrets in API responses | PASS | Health endpoint contains no secret material |
| No secrets in logs | PASS | Golden Rule #4: only correlation_id, error_code, status, path, user_id, workspace_id, latency_ms |

### G. Security Headers

| Check | Status | Notes |
|-------|--------|-------|
| X-Content-Type-Options: nosniff | PASS | Set by Caddy configuration |
| X-Frame-Options: DENY | PASS | Set by Caddy configuration |
| Strict-Transport-Security | PASS | HSTS header present via Caddy |
| Content-Security-Policy | **ADVISORY** | Recommended for web UI; API-only endpoints less critical |

### H. CSRF Protection

| Check | Status | Notes |
|-------|--------|-------|
| State-changing endpoints CSRF-aware | PASS | CSRF middleware on POST/PATCH/DELETE (Golden Rule #6) |
| Missing/wrong CSRF token → 403 | PASS | Enforced by middleware |

### I. Biometric Data Protection

| Check | Status | Notes |
|-------|--------|-------|
| Face embeddings encrypted at rest | **MANUAL** | Verify FACE_EMBED_KEY is set; face_detections.embedding_encrypted column contains Fernet-encrypted bytes, not raw floats |
| Hard-delete on consent revocation | **MANUAL** | Revoke face consent → verify zero rows in face_detections, face_clusters for that person. Only exception to soft-delete rule (Golden Rule #8) |

## Items Requiring Manual Testing

| Item | How to Test | Documented In |
|------|-------------|---------------|
| Workspace isolation with 2 users | Create 2 users in different workspaces, verify User A cannot see User B's data | ART-14 §16.3 |
| Face embedding encryption | Query face_detections directly, verify embedding_encrypted is Fernet ciphertext | ART-14 §13.2 |
| Consent revocation hard-delete | Revoke consent via API, verify biometric rows are physically deleted | ART-14 §13.3 |
| External pen test | Engage third-party security firm for network-level testing | ART-14 §16.5 |

## Supply Chain Status (ART-24)

| Check | Status | Script |
|-------|--------|--------|
| SBOM generated (SPDX) | PASS | `scripts/sbom/generate_sbom.sh` |
| License audit clean | PASS | `scripts/sbom/license_audit.sh` |
| Docker image pins verified | PASS | `scripts/sbom/verify_image_pins.sh` (via `security.yml`) |
| All lockfiles committed | PASS | `poetry.lock`, `pnpm-lock.yaml`, `Cargo.lock` in git |
| Zero GPL/AGPL without approval | PASS | Only MIT/Apache-2.0/BSD dependencies |

## Conclusion

EkamCore meets all automated security checks from ART-14 §19. Three items
require manual verification (workspace isolation, biometric encryption, consent
revocation). The supply chain audit (ART-24) is clean with no restrictive
license dependencies.
