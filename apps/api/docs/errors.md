# Error Code Reference (S10-002)

Every API error response has this shape:

```json
{
  "error_code": "AUTH_INVALID_CREDENTIALS",
  "message": "Invalid email or password.",
  "details": {},
  "correlation_id": "uuid"
}
```

The canonical registry is `api/errors_registry.py`. Web and mobile clients
mirror this mapping for user-friendly messages.

---

## Authentication

| Code | HTTP | Message |
|------|------|---------|
| `AUTH_INVALID_CREDENTIALS` | 401 | Invalid email or password. |
| `AUTH_TOKEN_MISSING` | 401 | Authentication token is missing. |
| `AUTH_TOKEN_INVALID` | 401 | Authentication token is invalid. |
| `AUTH_TOKEN_EXPIRED` | 401 | Your session has expired. Please sign in again. |
| `AUTH_SESSION_REVOKED` | 401 | Your session has been revoked. |
| `AUTH_REFRESH_MISSING` | 401 | Refresh token is missing. |
| `AUTH_REFRESH_INVALID` | 401 | Refresh token is invalid. |
| `AUTH_REFRESH_EXPIRED` | 401 | Refresh token has expired. Please sign in again. |
| `AUTH_REFRESH_REVOKED` | 401 | Refresh token has been revoked. |
| `AUTH_ACCOUNT_LOCKED` | 423 | Account temporarily locked due to too many failed attempts. |

## Authorization

| Code | HTTP | Message |
|------|------|---------|
| `WORKSPACE_ACCESS_DENIED` | 403 | You do not have access to this workspace. |
| `ADMIN_REQUIRED` | 403 | Admin role required for this endpoint. |
| `CSRF_VALIDATION_FAILED` | 403 | CSRF validation failed. Please refresh and try again. |
| `FEATURE_DISABLED` | 403 | This feature is not enabled. |
| `NO_WORKSPACE` | 403 | No workspace found for this user. |

## Validation

| Code | HTTP | Message |
|------|------|---------|
| `VALIDATION_ERROR` | 422 | The request contains invalid data. |
| `SOURCE_PATH_REQUIRED` | 422 | A file path is required for this source type. |
| `SOURCE_PATH_NOT_FOUND` | 422 | The specified path does not exist. |
| `SOURCE_TYPE_MISMATCH` | 422 | Source type does not match the expected value. |

## Not Found

| Code | HTTP | Message |
|------|------|---------|
| `NOT_FOUND` | 404 | The requested resource was not found. |
| `SOURCE_NOT_FOUND` | 404 | Source not found. |
| `DOCUMENT_NOT_FOUND` | 404 | Document not found. |
| `PHOTO_NOT_FOUND` | 404 | Photo not found. |
| `THUMBNAIL_NOT_FOUND` | 404 | Photo thumbnail not found. |
| `JOB_NOT_FOUND` | 404 | Job not found or not in a retryable state. |

## Conflict

| Code | HTTP | Message |
|------|------|---------|
| `SOURCE_DUPLICATE` | 409 | A source with this name already exists. |

## Rate Limiting

| Code | HTTP | Message |
|------|------|---------|
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests. Please slow down. |

## External Services

| Code | HTTP | Message |
|------|------|---------|
| `PAPERLESS_UNAVAILABLE` | 503 | Document service is temporarily unavailable. |
| `PAPERLESS_AUTH_FAILED` | 503 | Document service authentication failed. |
| `EMBEDDER_UNAVAILABLE` | 503 | Embedding service is temporarily unavailable. |
| `EMBEDDER_BAD_RESPONSE` | 503 | Embedding service returned an invalid response. |
| `LLM_UNAVAILABLE` | 503 | AI features are starting up. Please try again in a moment. |
| `LLM_TIMEOUT` | 503 | AI response took too long. Try a simpler question. |
| `LLM_ERROR` | 503 | AI service encountered an error. |
| `LLM_EMPTY_RESPONSE` | 503 | AI returned an empty response. Please try again. |

## Internal

| Code | HTTP | Message |
|------|------|---------|
| `INTERNAL_ERROR` | 500 | An internal error occurred. |
| `SERVICE_UNAVAILABLE` | 503 | Service is temporarily unavailable. |
| `WRITE_THROUGH_FAILED` | 502 | A background write operation failed. |
