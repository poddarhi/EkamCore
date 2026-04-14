"""Canonical error code registry (S10-002).

Single source of truth for every error_code returned by the API.
The web and mobile clients mirror this mapping for user-friendly messages.

Usage:
  from api.errors_registry import ERROR_CODES
  msg = ERROR_CODES["AUTH_INVALID_CREDENTIALS"]["message"]
"""

from __future__ import annotations

from typing import TypedDict


class ErrorDef(TypedDict):
    status: int
    message: str
    category: str  # auth, validation, resource, service, internal


ERROR_CODES: dict[str, ErrorDef] = {
    # ── Base class defaults (always overridden with specific codes) ──
    "AUTHENTICATION_ERROR": {
        "status": 401,
        "message": "Authentication required.",
        "category": "auth",
    },
    "AUTHORIZATION_ERROR": {
        "status": 403,
        "message": "You are not authorized to perform this action.",
        "category": "auth",
    },
    "CONFLICT": {
        "status": 409,
        "message": "The request conflicts with the current state.",
        "category": "resource",
    },

    # ── Authentication ──
    "AUTH_INVALID_CREDENTIALS": {
        "status": 401,
        "message": "Invalid email or password.",
        "category": "auth",
    },
    "AUTH_TOKEN_MISSING": {
        "status": 401,
        "message": "Authentication token is missing.",
        "category": "auth",
    },
    "AUTH_TOKEN_INVALID": {
        "status": 401,
        "message": "Authentication token is invalid.",
        "category": "auth",
    },
    "AUTH_TOKEN_EXPIRED": {
        "status": 401,
        "message": "Your session has expired. Please sign in again.",
        "category": "auth",
    },
    "AUTH_SESSION_REVOKED": {
        "status": 401,
        "message": "Your session has been revoked.",
        "category": "auth",
    },
    "AUTH_REFRESH_MISSING": {
        "status": 401,
        "message": "Refresh token is missing.",
        "category": "auth",
    },
    "AUTH_REFRESH_INVALID": {
        "status": 401,
        "message": "Refresh token is invalid.",
        "category": "auth",
    },
    "AUTH_REFRESH_EXPIRED": {
        "status": 401,
        "message": "Refresh token has expired. Please sign in again.",
        "category": "auth",
    },
    "AUTH_REFRESH_REVOKED": {
        "status": 401,
        "message": "Refresh token has been revoked.",
        "category": "auth",
    },
    "AUTH_ACCOUNT_LOCKED": {
        "status": 423,
        "message": "Account temporarily locked due to too many failed attempts.",
        "category": "auth",
    },

    # ── Authorization ──
    "WORKSPACE_ACCESS_DENIED": {
        "status": 403,
        "message": "You do not have access to this workspace.",
        "category": "auth",
    },
    "ADMIN_REQUIRED": {
        "status": 403,
        "message": "Admin role required for this endpoint.",
        "category": "auth",
    },
    "CSRF_VALIDATION_FAILED": {
        "status": 403,
        "message": "CSRF validation failed. Please refresh and try again.",
        "category": "auth",
    },
    "FEATURE_DISABLED": {
        "status": 403,
        "message": "This feature is not enabled.",
        "category": "auth",
    },
    "NO_WORKSPACE": {
        "status": 403,
        "message": "No workspace found for this user.",
        "category": "auth",
    },

    # ── Validation ──
    "VALIDATION_ERROR": {
        "status": 422,
        "message": "The request contains invalid data.",
        "category": "validation",
    },
    "SOURCE_PATH_REQUIRED": {
        "status": 422,
        "message": "A file path is required for this source type.",
        "category": "validation",
    },
    "SOURCE_PATH_NOT_FOUND": {
        "status": 422,
        "message": "The specified path does not exist.",
        "category": "validation",
    },
    "SOURCE_TYPE_MISMATCH": {
        "status": 422,
        "message": "Source type does not match the expected value.",
        "category": "validation",
    },

    # ── Not Found ──
    "NOT_FOUND": {
        "status": 404,
        "message": "The requested resource was not found.",
        "category": "resource",
    },
    "SOURCE_NOT_FOUND": {
        "status": 404,
        "message": "Source not found.",
        "category": "resource",
    },
    "DOCUMENT_NOT_FOUND": {
        "status": 404,
        "message": "Document not found.",
        "category": "resource",
    },
    "PHOTO_NOT_FOUND": {
        "status": 404,
        "message": "Photo not found.",
        "category": "resource",
    },
    "PHOTO_ASSET_NOT_FOUND": {
        "status": 404,
        "message": "Photo asset record not found.",
        "category": "resource",
    },
    "PHOTO_FILE_NOT_FOUND": {
        "status": 404,
        "message": "Underlying file row for photo asset is missing.",
        "category": "resource",
    },
    "THUMBNAIL_NOT_FOUND": {
        "status": 404,
        "message": "Photo thumbnail not found.",
        "category": "resource",
    },
    "JOB_NOT_FOUND": {
        "status": 404,
        "message": "Job not found or not in a retryable state.",
        "category": "resource",
    },

    # ── Conflict ──
    "SOURCE_DUPLICATE": {
        "status": 409,
        "message": "A source with this name already exists.",
        "category": "resource",
    },
    "CONSENT_VERSION_STALE": {
        "status": 409,
        "message": (
            "The consent text has been updated. "
            "Please review the new text and re-submit."
        ),
        "category": "auth",
    },
    "BACKFILL_ALREADY_RUNNING": {
        "status": 409,
        "message": "A face backfill is already in progress for this workspace.",
        "category": "resource",
    },
    "BACKFILL_NOT_RUNNING": {
        "status": 404,
        "message": "No face backfill is currently running for this workspace.",
        "category": "resource",
    },
    "CONSENT_NOT_ACCEPTED": {
        "status": 409,
        "message": "Consent must be explicitly accepted.",
        "category": "auth",
    },
    "FACE_HARD_DELETE_PRECOUNT_FAILED": {
        "status": 503,
        "message": "Could not read face data counts prior to deletion.",
        "category": "service",
    },
    "FACE_HARD_DELETE_QDRANT_FAILED": {
        "status": 503,
        "message": "Qdrant delete-by-filter failed. Revocation rolled back.",
        "category": "service",
    },
    "FACE_HARD_DELETE_QDRANT_VERIFY_FAILED": {
        "status": 503,
        "message": "Qdrant post-delete count failed. Revocation rolled back.",
        "category": "service",
    },
    "FACE_HARD_DELETE_QDRANT_RESIDUE": {
        "status": 503,
        "message": (
            "Qdrant still reports points after delete-by-filter. "
            "Revocation rolled back."
        ),
        "category": "service",
    },
    "FACE_HARD_DELETE_PG_DETECTIONS_FAILED": {
        "status": 503,
        "message": "PG delete of face_detections failed. Revocation rolled back.",
        "category": "service",
    },
    "FACE_HARD_DELETE_PG_CLUSTERS_FAILED": {
        "status": 503,
        "message": "PG delete of face_clusters failed. Revocation rolled back.",
        "category": "service",
    },
    "FACE_HARD_DELETE_PG_PHOTO_COUNT_FAILED": {
        "status": 503,
        "message": "PG update of photo_asset.face_count failed. Revocation rolled back.",
        "category": "service",
    },
    "FACE_HARD_DELETE_AUDIT_FAILED": {
        "status": 503,
        "message": "Audit row write failed after successful deletion. Revocation rolled back.",
        "category": "service",
    },
    "FACE_CLUSTERING_FAILED": {
        "status": 503,
        "message": "Face clustering failed. Please try again.",
        "category": "service",
    },
    "FACE_CLUSTERING_LIB_UNAVAILABLE": {
        "status": 503,
        "message": "Face clustering library is not installed in this environment.",
        "category": "service",
    },
    "FACE_DETECTION_NOT_FOUND": {
        "status": 404,
        "message": "Face detection record not found.",
        "category": "resource",
    },
    "FACE_CLUSTER_NOT_FOUND": {
        "status": 404,
        "message": "Face cluster not found.",
        "category": "resource",
    },
    "CANDIDATE_SCORING_FAILED": {
        "status": 503,
        "message": "Candidate contact scoring failed. Please try again.",
        "category": "service",
    },

    # ── Rate Limiting ──
    "RATE_LIMIT_EXCEEDED": {
        "status": 429,
        "message": "Too many requests. Please slow down.",
        "category": "service",
    },

    # ── External Services ──
    "PAPERLESS_UNAVAILABLE": {
        "status": 503,
        "message": "Document service is temporarily unavailable.",
        "category": "service",
    },
    "PAPERLESS_AUTH_FAILED": {
        "status": 503,
        "message": "Document service authentication failed.",
        "category": "service",
    },
    "EMBEDDER_UNAVAILABLE": {
        "status": 503,
        "message": "Embedding service is temporarily unavailable.",
        "category": "service",
    },
    "EMBEDDER_BAD_RESPONSE": {
        "status": 503,
        "message": "Embedding service returned an invalid response.",
        "category": "service",
    },
    "LLM_UNAVAILABLE": {
        "status": 503,
        "message": "AI features are starting up. Please try again in a moment.",
        "category": "service",
    },
    "LLM_TIMEOUT": {
        "status": 503,
        "message": "AI response took too long. Try a simpler question.",
        "category": "service",
    },
    "LLM_ERROR": {
        "status": 503,
        "message": "AI service encountered an error.",
        "category": "service",
    },
    "LLM_EMPTY_RESPONSE": {
        "status": 503,
        "message": "AI returned an empty response. Please try again.",
        "category": "service",
    },

    # ── Face pipeline (S11-001) ──
    "FACE_ENCRYPTION_KEY_MISSING": {
        "status": 503,
        "message": "Face pipeline is not configured. Contact your administrator.",
        "category": "service",
    },
    "FACE_ENCRYPTION_KEY_INVALID": {
        "status": 503,
        "message": "Face pipeline encryption key is invalid.",
        "category": "service",
    },
    "FACE_EMBEDDING_DECRYPT_FAILED": {
        "status": 503,
        "message": "Could not decrypt a face embedding. Key may have changed.",
        "category": "service",
    },
    "FACE_EMBEDDING_CORRUPT": {
        "status": 503,
        "message": "A stored face embedding appears to be corrupt.",
        "category": "service",
    },
    "FACE_CONSENT_REQUIRED": {
        "status": 403,
        "message": (
            "Face clustering requires your explicit consent. "
            "Enable it in Settings \u2192 Photo Intelligence."
        ),
        "category": "auth",
    },
    "FACE_MODEL_NOT_LOADED": {
        "status": 503,
        "message": "Face detection model is not loaded yet. Try again shortly.",
        "category": "service",
    },
    "FACE_MODEL_LOAD_FAILED": {
        "status": 503,
        "message": "Face detection model could not be loaded. Check server logs.",
        "category": "service",
    },
    "FACE_MODEL_INVALID_IMAGE": {
        "status": 422,
        "message": "Face detection could not decode the provided image.",
        "category": "validation",
    },

    # ── Trusted Persons / People Graph (S12-004) ──
    "PERSON_NOT_FOUND": {
        "status": 404,
        "message": "Trusted person not found.",
        "category": "resource",
    },
    "CLUSTER_NOT_FOUND": {
        "status": 404,
        "message": "Cluster not found in this workspace.",
        "category": "resource",
    },
    "INVALID_CANDIDATE": {
        "status": 422,
        "message": "Contact is not one of this cluster's candidates.",
        "category": "validation",
    },
    "INVALID_MERGE_KEEPER": {
        "status": 422,
        "message": "keeper_id must be one of the merged person_ids.",
        "category": "validation",
    },
    "SPLIT_FACES_NOT_FOUND": {
        "status": 422,
        "message": "One or more face_detections do not belong to the given person.",
        "category": "validation",
    },
    "OPERATION_NOT_FOUND": {
        "status": 404,
        "message": "Operation not found.",
        "category": "resource",
    },
    "OPERATION_ALREADY_UNDONE": {
        "status": 409,
        "message": "Operation has already been undone.",
        "category": "validation",
    },

    # ── Internal ──
    "INTERNAL_ERROR": {
        "status": 500,
        "message": "An internal error occurred.",
        "category": "internal",
    },
    "SERVICE_UNAVAILABLE": {
        "status": 503,
        "message": "Service is temporarily unavailable.",
        "category": "internal",
    },
    "WRITE_THROUGH_FAILED": {
        "status": 502,
        "message": "A background write operation failed.",
        "category": "internal",
    },
}
