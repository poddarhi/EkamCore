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

// ── Auth state sync (AuthContext registers these) ──
type AuthChangeHandler = (token: string) => void;
type AuthFailHandler = () => void;

let _onTokenRefreshed: AuthChangeHandler | null = null;
let _onRefreshFailed: AuthFailHandler | null = null;

/**
 * Called by AuthContext on mount so the client can notify it
 * when a 401-triggered refresh succeeds or fails.
 */
export function registerAuthCallbacks(
  onRefreshed: AuthChangeHandler,
  onFailed: AuthFailHandler,
) {
  _onTokenRefreshed = onRefreshed;
  _onRefreshFailed = onFailed;
}

export function unregisterAuthCallbacks() {
  _onTokenRefreshed = null;
  _onRefreshFailed = null;
}

// ── Error messages (delegated to utils/errorMessages.ts) ──
import { getUserMessage as _getUserMessage } from "../utils/errorMessages";
export const getUserMessage = _getUserMessage;

// ── CSRF helpers ──

const CSRF_COOKIE_NAME = "ekamcore_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";
const MUTATING_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

/**
 * Read a cookie value by name from document.cookie. Returns null if
 * the cookie is not set or if we're in an SSR/test context without
 * document.
 */
function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const pairs = document.cookie ? document.cookie.split("; ") : [];
  for (const pair of pairs) {
    const eq = pair.indexOf("=");
    if (eq === -1) continue;
    if (pair.slice(0, eq) === name) {
      return decodeURIComponent(pair.slice(eq + 1));
    }
  }
  return null;
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

  // CSRF: auto-send the ekamcore_csrf cookie as X-CSRF-Token for
  // mutating methods. The server validates double-submit by comparing
  // the header against the same-named cookie set at login time.
  // Skipped for /auth/login (CSRF-exempt because no session yet);
  // explicit header overrides remain intact.
  const method = (options.method || "GET").toUpperCase();
  if (
    MUTATING_METHODS.has(method) &&
    !headers.has(CSRF_HEADER_NAME) &&
    !url.endsWith("/auth/login")
  ) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
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
    if (!res.ok) {
      _onRefreshFailed?.();
      return false;
    }
    const data = await res.json();
    accessToken = data.access_token;
    _onTokenRefreshed?.(data.access_token);
    return true;
  } catch {
    _onRefreshFailed?.();
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

// ── JWT helpers ──

/** Extract the `exp` (seconds since epoch) from a JWT without verifying. */
export function getTokenExp(token: string): number | null {
  try {
    const base64 = token.split(".")[1];
    const payload = JSON.parse(atob(base64));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

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

// ── Search types ──

export interface PaginationInfo {
  cursor: number;
  has_more: boolean;
}

export interface SearchResponse {
  data: Card[];
  pagination: PaginationInfo;
  facets: Record<string, number>;
}

export type SearchType = "calendar" | "reminder" | "contact" | "file" | "photo" | "all";

export interface FilePayload {
  filename?: string | null;
  path?: string | null;
  snippet?: string | null;        // highlighted content excerpt
  correspondent?: string | null;
  tags?: string[];
  document_type?: string | null;
  modified_date?: string | null;
  paperless_id?: number | string | null;
  mime_type?: string | null;
}

export interface PhotoPayload {
  photo_id?: string | null;
  thumbnail_url?: string | null;
  taken_at?: string | null;
  location_name?: string | null;
  camera?: string | null;
  width?: number | null;
  height?: number | null;
}

// ── Health types ──

export interface ServiceHealth {
  status: "healthy" | "unhealthy";
  error?: string;
}

export interface HealthResponse {
  status: "healthy" | "degraded";
  services: Record<string, ServiceHealth>;
  version: string;
  ram_mode: string;
  note?: string;
}
