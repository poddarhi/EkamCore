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
