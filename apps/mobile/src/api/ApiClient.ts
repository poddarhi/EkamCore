/**
 * ApiClient — class-based HTTP client with auth, retry, CSRF, and
 * configurable base URL (S16-001).
 *
 * Wraps the existing apiFetch pattern in a class that adds:
 * - Configurable base URL (for Tailscale IP discovery)
 * - Exponential backoff retry (500ms → 1s → 2s, 3 attempts)
 * - CSRF token auto-fetch for state-changing methods
 * - Per-connectivity-state timeouts via config/api.ts
 * - Deduplication of concurrent 401 refresh attempts
 *
 * Access token is kept in memory only (never persisted).
 * Refresh token is in Keychain via TokenManager.
 */

import {
  API_BASE_URL,
  RETRY_CONFIG,
  getTimeouts,
} from '../config/api';
import {ConnectivityManager} from '../services/ConnectivityManager';
import {TokenManager} from '../services/TokenManager';

// ── Types ───────────────────────────────────────────────────────────────────

export interface RequestConfig {
  path: string;
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  /** Override timeout (ms). Defaults to connectivity-aware value. */
  timeoutMs?: number;
  /** Skip retry logic for this request. */
  noRetry?: boolean;
}

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

// ── Client ──────────────────────────────────────────────────────────────────

class ApiClientClass {
  private baseUrl: string = API_BASE_URL;
  private accessToken: string | null = null;
  private csrfToken: string | null = null;
  private refreshPromise: Promise<boolean> | null = null;
  private onAuthFailure: (() => void) | null = null;

  // ── Configuration ──

  setBaseUrl(url: string): void {
    this.baseUrl = url.replace(/\/+$/, '');
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  setAuthToken(token: string | null): void {
    this.accessToken = token;
  }

  getAuthToken(): string | null {
    return this.accessToken;
  }

  clearAuth(): void {
    this.accessToken = null;
    this.csrfToken = null;
  }

  /** Register a callback invoked when auth fails irrecoverably (navigate to login). */
  setOnAuthFailure(cb: (() => void) | null): void {
    this.onAuthFailure = cb;
  }

  // ── Main request method ──

  async request<T>(config: RequestConfig): Promise<T> {
    const method = config.method ?? 'GET';
    const isMutation = method !== 'GET';

    // Fetch CSRF token for mutations if we don't have one
    if (isMutation && !this.csrfToken) {
      await this.fetchCsrfToken();
    }

    // Determine timeout from connectivity state
    const connState = ConnectivityManager.getState();
    const timeouts = getTimeouts(connState);
    const timeoutMs = config.timeoutMs ?? (isMutation ? timeouts.request * 3 : timeouts.request);

    // Retry loop
    const maxAttempts = config.noRetry ? 1 : RETRY_CONFIG.maxRetries + 1;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      if (attempt > 0) {
        const delay = RETRY_CONFIG.baseDelayMs * Math.pow(2, attempt - 1); // 500, 1000, 2000
        await sleep(delay);
      }

      try {
        return await this.doRequest<T>(config, method, timeoutMs);
      } catch (err) {
        lastError = err as Error;

        // Don't retry on auth errors or client errors (4xx)
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
          throw err;
        }

        // Retry on network errors and 5xx
        if (attempt < maxAttempts - 1) {
          continue;
        }
      }
    }

    throw lastError ?? new Error('Request failed');
  }

  // ── Internal request execution ──

  private async doRequest<T>(
    config: RequestConfig,
    method: string,
    timeoutMs: number,
  ): Promise<T> {
    const url = config.path.startsWith('http')
      ? config.path
      : `${this.baseUrl}${config.path}`;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...config.headers,
    };

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    if (this.csrfToken && method !== 'GET') {
      headers['X-CSRF-Token'] = this.csrfToken;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let res: Response;
    try {
      res = await fetch(url, {
        method,
        headers,
        body: config.body ? JSON.stringify(config.body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timer);
      if ((err as Error).name === 'AbortError') {
        throw new ApiError(0, 'TIMEOUT', `Request timed out after ${timeoutMs}ms`);
      }
      throw new ApiError(0, 'NETWORK_ERROR', 'Network request failed');
    } finally {
      clearTimeout(timer);
    }

    // Handle 401 — attempt one refresh
    if (res.status === 401 && this.accessToken) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        // Retry with new token
        headers['Authorization'] = `Bearer ${this.accessToken}`;
        res = await fetch(url, {
          method,
          headers,
          body: config.body ? JSON.stringify(config.body) : undefined,
        });
      } else {
        // Refresh failed — clear auth and notify
        this.clearAuth();
        this.onAuthFailure?.();
        throw new ApiError(401, 'AUTH_TOKEN_EXPIRED', 'Session expired. Please sign in again.');
      }
    }

    if (!res.ok) {
      throw await this.parseError(res);
    }

    if (res.status === 204) {
      return undefined as T;
    }

    return res.json() as Promise<T>;
  }

  // ── CSRF ──

  private async fetchCsrfToken(): Promise<void> {
    try {
      const url = `${this.baseUrl.replace('/api/v1', '')}/auth/csrf`;
      const res = await fetch(url, {
        method: 'GET',
        headers: this.accessToken
          ? {Authorization: `Bearer ${this.accessToken}`}
          : {},
      });
      if (res.ok) {
        const data = await res.json();
        this.csrfToken = data.csrf_token ?? data.token ?? null;
      }
    } catch {
      // CSRF fetch is best-effort — some deployments may not require it
    }
  }

  // ── Token refresh (deduplicated) ──

  private async tryRefresh(): Promise<boolean> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = this.doRefresh().finally(() => {
      this.refreshPromise = null;
    });

    return this.refreshPromise;
  }

  private async doRefresh(): Promise<boolean> {
    const refreshToken = await TokenManager.loadRefreshToken();
    if (!refreshToken) return false;

    try {
      const url = `${this.baseUrl.replace('/api/v1', '')}/auth/refresh`;
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${refreshToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) return false;

      const data = await res.json();
      if (data.access_token) {
        this.accessToken = data.access_token;
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  // ── Error parsing ──

  private async parseError(res: Response): Promise<ApiError> {
    try {
      const body = await res.json();
      return new ApiError(
        res.status,
        body.error_code ?? 'UNKNOWN',
        body.message ?? `HTTP ${res.status}`,
        body.correlation_id,
      );
    } catch {
      return new ApiError(res.status, 'UNKNOWN', `HTTP ${res.status}`);
    }
  }
}

// ── Helpers ──

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Singleton export ──

export const apiClient = new ApiClientClass();
