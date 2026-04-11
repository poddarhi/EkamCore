/**
 * Error code → user-friendly message mapping (S10-002).
 *
 * Mirrors api/errors_registry.py.  Keep these in sync when adding
 * new error codes to the backend.
 */

const ERROR_MESSAGES: Record<string, string> = {
  // Authentication
  AUTH_INVALID_CREDENTIALS: "Incorrect email or password.",
  AUTH_TOKEN_MISSING: "Please sign in to continue.",
  AUTH_TOKEN_INVALID: "Your session is invalid. Please sign in again.",
  AUTH_TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
  AUTH_SESSION_REVOKED: "Your session has been revoked. Please sign in again.",
  AUTH_REFRESH_MISSING: "Your session could not be restored. Please sign in.",
  AUTH_REFRESH_INVALID: "Your session could not be restored. Please sign in.",
  AUTH_REFRESH_EXPIRED: "Your session has expired. Please sign in again.",
  AUTH_REFRESH_REVOKED: "Your session has been revoked. Please sign in again.",
  AUTH_ACCOUNT_LOCKED:
    "Too many failed attempts. Your account is temporarily locked. Try again in a few minutes.",

  // Authorization
  WORKSPACE_ACCESS_DENIED: "You don't have access to this workspace.",
  ADMIN_REQUIRED: "This action requires admin privileges.",
  CSRF_VALIDATION_FAILED: "Security validation failed. Please refresh the page and try again.",
  FEATURE_DISABLED: "This feature is not yet available.",
  NO_WORKSPACE: "No workspace found. Please contact your administrator.",

  // Validation
  VALIDATION_ERROR: "Some fields are invalid. Please check and try again.",
  SOURCE_PATH_REQUIRED: "A file path is required.",
  SOURCE_PATH_NOT_FOUND: "The specified folder doesn't exist.",
  SOURCE_TYPE_MISMATCH: "The source type doesn't match.",

  // Not found
  NOT_FOUND: "The requested item was not found.",
  SOURCE_NOT_FOUND: "Source not found.",
  DOCUMENT_NOT_FOUND: "Document not found.",
  PHOTO_NOT_FOUND: "Photo not found.",
  THUMBNAIL_NOT_FOUND: "Photo thumbnail not available.",
  JOB_NOT_FOUND: "Job not found or not in a retryable state.",

  // Conflict
  SOURCE_DUPLICATE: "A source with this name already exists.",

  // Rate limiting
  RATE_LIMIT_EXCEEDED: "Slow down — you're sending too many requests. Please wait a moment.",

  // External services
  PAPERLESS_UNAVAILABLE: "Document service is temporarily unavailable. Try again shortly.",
  PAPERLESS_AUTH_FAILED: "Could not authenticate with the document service.",
  EMBEDDER_UNAVAILABLE: "Search indexing service is temporarily unavailable.",
  EMBEDDER_BAD_RESPONSE: "Search indexing returned an unexpected result.",
  LLM_UNAVAILABLE: "AI features are starting up. Please try again in a moment.",
  LLM_TIMEOUT: "AI response took too long. Try a simpler question.",
  LLM_ERROR: "AI service encountered an error. Please try again.",
  LLM_EMPTY_RESPONSE: "AI returned an empty response. Please try again.",

  // Internal
  INTERNAL_ERROR: "Something went wrong. Please try again.",
  SERVICE_UNAVAILABLE: "Service is temporarily unavailable. Please try again shortly.",
  WRITE_THROUGH_FAILED: "A background operation failed. Your changes may be delayed.",
};

/**
 * Get a user-friendly message for an API error code.
 *
 * @param errorCode - The error_code from the API response.
 * @param detail - Optional detail string to append (e.g., retry-after seconds).
 * @returns User-friendly message string.
 */
export function getUserMessage(errorCode: string, detail?: string): string {
  const base = ERROR_MESSAGES[errorCode] ?? "An unexpected error occurred.";
  return detail ? `${base} ${detail}` : base;
}

/**
 * Check if an error code is an auth error that should trigger re-login.
 */
export function isAuthError(errorCode: string): boolean {
  return errorCode.startsWith("AUTH_") && errorCode !== "AUTH_ACCOUNT_LOCKED";
}

/**
 * Check if an error code is a transient service error (toast-worthy, not banner-worthy).
 */
export function isTransientError(errorCode: string): boolean {
  return [
    "LLM_UNAVAILABLE",
    "LLM_TIMEOUT",
    "LLM_ERROR",
    "LLM_EMPTY_RESPONSE",
    "EMBEDDER_UNAVAILABLE",
    "PAPERLESS_UNAVAILABLE",
    "RATE_LIMIT_EXCEEDED",
    "SERVICE_UNAVAILABLE",
  ].includes(errorCode);
}
