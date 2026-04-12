"""Face clustering consent text — legal source of truth (S11-002).

Legal Advisor edits ONLY this file. Bumping CURRENT_CONSENT_VERSION forces
all workspaces with an older consent record to re-consent before the face
pipeline resumes.

Written against the ART-15 §3 disclosure checklist. Marked DRAFT pending
Legal Advisor review — the version string MUST retain the -DRAFT marker
until legal signs off.

Any change to the visible text body MUST bump CURRENT_CONSENT_VERSION so
that existing consent records are treated as expired.
"""

from __future__ import annotations

CURRENT_CONSENT_VERSION: str = "v1.0-DRAFT-2026-04"

CURRENT_CONSENT_TEXT: str = """\
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

───────────────────────────────────────────────────────────────
DRAFT — PENDING LEGAL ADVISOR REVIEW
───────────────────────────────────────────────────────────────
This consent text is a draft prepared against the ART-15 §3
disclosure checklist. It must be reviewed and approved by the
project's Legal Advisor before the DRAFT marker is removed and
before face clustering is made available to end users.
"""


def get_current_text() -> str:
    """Return the current consent text body. Use this rather than the
    module-level constant when rendering, so future extensions (e.g.
    locale selection) can hook here without touching callers."""
    return CURRENT_CONSENT_TEXT


def get_current_version() -> str:
    """Return the current consent version string."""
    return CURRENT_CONSENT_VERSION
