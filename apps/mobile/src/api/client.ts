/**
 * Mobile API client.
 *
 * Access token is kept in memory (never AsyncStorage).
 * Refresh token is stored in react-native-keychain via TokenManager.
 * On 401, attempts one silent refresh via /api/v1/auth/refresh before failing.
 */

const API_BASE = 'https://localhost/api/v1';
const HEALTH_URL = 'https://localhost/health';

export {API_BASE, HEALTH_URL};

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
    this.name = 'ApiError';
    this.status = status;
    this.errorCode = errorCode;
    this.correlationId = correlationId;
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  AUTH_INVALID_CREDENTIALS: 'Invalid email or password.',
  AUTH_ACCOUNT_LOCKED:
    'Account temporarily locked due to too many failed attempts. Try again later.',
  AUTH_TOKEN_EXPIRED: 'Your session has expired. Please sign in again.',
  AUTH_UNAUTHORIZED: 'You must be signed in to access this.',
  INTERNAL_ERROR: 'Something went wrong. Please try again.',
};

export function getUserMessage(errorCode: string): string {
  return ERROR_MESSAGES[errorCode] ?? 'An unexpected error occurred.';
}

// ── In-memory token ──
let accessToken: string | null = null;
let refreshCallback: (() => Promise<boolean>) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Register the refresh function (called by AuthContext on mount). */
export function registerRefreshCallback(
  cb: (() => Promise<boolean>) | null,
): void {
  refreshCallback = cb;
}

/** Extract the `exp` (seconds since epoch) from a JWT without verifying. */
export function getTokenExp(token: string): number | null {
  try {
    const base64 = token.split('.')[1];
    const decoded = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
    const payload = JSON.parse(decoded);
    return typeof payload.exp === 'number' ? payload.exp : null;
  } catch {
    return null;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    return new ApiError(
      res.status,
      body.error_code ?? 'UNKNOWN',
      getUserMessage(body.error_code ?? 'UNKNOWN'),
      body.correlation_id,
    );
  } catch {
    return new ApiError(res.status, 'UNKNOWN', 'An unexpected error occurred.');
  }
}

function buildHeaders(extra?: Record<string, string>): Headers {
  const h = new Headers(extra);
  if (accessToken) {
    h.set('Authorization', `Bearer ${accessToken}`);
  }
  if (!h.has('Content-Type')) {
    h.set('Content-Type', 'application/json');
  }
  return h;
}

// Deduplicate concurrent refresh attempts
let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshCallback) return false;
  if (!refreshPromise) {
    refreshPromise = refreshCallback().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;

  let res = await fetch(url, {
    ...options,
    headers: buildHeaders(options.headers as Record<string, string>),
  });

  if (res.status === 401 && accessToken) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await fetch(url, {
        ...options,
        headers: buildHeaders(options.headers as Record<string, string>),
      });
    }
  }

  if (!res.ok) {
    throw await parseError(res);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}
