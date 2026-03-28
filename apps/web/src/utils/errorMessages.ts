/** Map API error_code to user-facing messages. */
const ERROR_MESSAGES: Record<string, string> = {
  AUTH_INVALID_CREDENTIALS: "Invalid email or password.",
  AUTH_ACCOUNT_LOCKED:
    "Account temporarily locked due to too many failed attempts. Try again later.",
  AUTH_TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
  AUTH_UNAUTHORIZED: "You must be signed in to access this.",
  CSRF_VALIDATION_FAILED: "Security validation failed. Please try again.",
  INTERNAL_ERROR: "Something went wrong. Please try again.",
};

export function getUserMessage(errorCode: string): string {
  return ERROR_MESSAGES[errorCode] ?? "An unexpected error occurred.";
}
