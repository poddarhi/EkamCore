/**
 * API client with auth interceptor and auto-refresh on 401.
 *
 * The access token is stored in a module-level variable (memory only — never localStorage).
 * On 401, the client attempts a token refresh via /api/v1/auth/refresh (cookie-based)
 * and retries the original request once.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly errorCode: string;
  readonly correlationId: string | undefined;

  constructor(
    status: number,
    errorCode: string,
    message: string,
    correlationId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = errorCode;
    this.correlationId = correlationId;
  }
}

// ── In-memory token store ──
let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

// ── Error code → user-friendly message ──
const ERROR_MESSAGES: Record<string, string> = {
  AUTH_INVALID_CREDENTIALS: "Invalid email or password.",
  AUTH_ACCOUNT_LOCKED:
    "Account temporarily locked due to too many failed attempts. Try again later.",
  AUTH_TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
  AUTH_UNAUTHORIZED: "You must be signed in to access this.",
  INTERNAL_ERROR: "Something went wrong. Please try again.",
};

export function getUserMessage(errorCode: string): string {
  return ERROR_MESSAGES[errorCode] ?? "An unexpected error occurred.";
}

// ── Core fetch wrapper ──
async function rawFetch(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(options.headers);

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(url, { ...options, headers, credentials: "include" });
}

async function parseErrorResponse(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    return new ApiError(
      res.status,
      body.error_code ?? "UNKNOWN",
      getUserMessage(body.error_code ?? "UNKNOWN"),
      body.correlation_id,
    );
  } catch {
    return new ApiError(res.status, "UNKNOWN", "An unexpected error occurred.");
  }
}

// ── Refresh logic ──
let refreshPromise: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  try {
    const res = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return false;
    const data = await res.json();
    accessToken = data.access_token;
    return true;
  } catch {
    return false;
  }
}

function refreshOnce(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = attemptRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

// ── Public API ──
export async function apiFetch<T = unknown>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  let res = await rawFetch(url, options);

  // Auto-refresh on 401
  if (res.status === 401 && accessToken) {
    const refreshed = await refreshOnce();
    if (refreshed) {
      res = await rawFetch(url, options);
    }
  }

  if (!res.ok) {
    throw await parseErrorResponse(res);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

/** SWR-compatible fetcher */
export const swrFetcher = <T = unknown>(url: string): Promise<T> =>
  apiFetch<T>(url);

// ── Response types ──

export interface SourceRef {
  type: "file" | "contact" | "event" | "reminder" | "photo" | "person";
  id: string;
  title: string;
  relevance: number;
}

export interface SuggestedAction {
  action_type: string;
  label: string;
  payload: Record<string, unknown>;
}

export interface ResponseMetadata {
  query_path: "deterministic" | "semantic" | "small_model" | "large_model";
  latency_ms: number;
  is_partial: boolean;
  cache_hint: { ttl_seconds: number } | null;
}

export interface EventPayload {
  title: string;
  start_at: string;
  end_at: string | null;
  is_all_day: boolean;
  location: string | null;
  calendar_name: string | null;
  participants: string[];
}

export interface ReminderPayload {
  title: string;
  due_at: string | null;
  priority: "high" | "medium" | "low" | "none" | null;
  list_name: string | null;
  notes: string | null;
  is_overdue: boolean;
}

export interface StatusPayload {
  date: string;
  time_of_day: "morning" | "afternoon" | "evening" | "night";
  weekday: string;
}

export interface Card {
  type: "event" | "reminder" | "status" | "person" | "file" | "photo" | "suggestion" | "pack";
  id: string;
  priority_score: number;
  source_ids: string[];
  payload: EventPayload | ReminderPayload | StatusPayload | Record<string, unknown>;
}

export interface ResponseEnvelope {
  answer_text: string | null;
  confidence_level: "deterministic" | "high" | "medium" | "low";
  sources: SourceRef[];
  cards: Card[];
  suggested_actions: SuggestedAction[];
  metadata: ResponseMetadata;
}
