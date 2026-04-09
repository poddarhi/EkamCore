/**
 * API configuration — base URL and per-connectivity-state timeouts.
 *
 * The mobile app connects to the EkamCore API via Tailscale (local network).
 * Timeouts are adjusted based on the current ConnectivityManager state to
 * provide snappy UX when connected and patient retries when degraded.
 */

import type {ConnectivityState} from '../services/ConnectivityManager';

// ── Base URL ──

/**
 * The EkamCore API runs on the user's Mac behind Tailscale.
 * In development, localhost; in production, the Tailscale MagicDNS hostname.
 */
export const API_BASE_URL = 'https://localhost/api/v1';

/**
 * Health endpoint (outside /api/v1 prefix).
 */
export const HEALTH_URL = 'https://localhost/health';

// ── Timeouts (milliseconds) ──

interface TimeoutConfig {
  /** Timeout for interactive requests (today, recap, search). */
  request: number;
  /** Timeout for auth requests (login, refresh). */
  auth: number;
  /** Timeout for health check polls. */
  health: number;
}

const TIMEOUT_CONNECTED: TimeoutConfig = {
  request: 10_000,
  auth: 10_000,
  health: 5_000,
};

const TIMEOUT_DEGRADED: TimeoutConfig = {
  request: 20_000,
  auth: 15_000,
  health: 10_000,
};

const TIMEOUT_RECONNECTING: TimeoutConfig = {
  request: 30_000,
  auth: 20_000,
  health: 15_000,
};

const TIMEOUT_DISCONNECTED: TimeoutConfig = {
  request: 5_000, // Fail fast — we know the server is down
  auth: 5_000,
  health: 10_000, // Keep probing
};

const TIMEOUTS: Record<ConnectivityState, TimeoutConfig> = {
  CONNECTED: TIMEOUT_CONNECTED,
  DEGRADED: TIMEOUT_DEGRADED,
  RECONNECTING: TIMEOUT_RECONNECTING,
  DISCONNECTED_CACHED: TIMEOUT_DISCONNECTED,
  DISCONNECTED_EMPTY: TIMEOUT_DISCONNECTED,
  HUB_SLEEPING: TIMEOUT_DISCONNECTED,
};

/**
 * Get timeout config for the current connectivity state.
 */
export function getTimeouts(state: ConnectivityState): TimeoutConfig {
  return TIMEOUTS[state];
}

// ── Retry config ──

export const RETRY_CONFIG = {
  /** Max retries for failed requests before surfacing the error. */
  maxRetries: 2,
  /** Base delay between retries (ms). Multiplied by attempt number. */
  baseDelayMs: 1_000,
} as const;

// ── SWR / polling intervals ──

export const REFRESH_INTERVALS = {
  /** Today page auto-refresh (ms). */
  today: 5 * 60 * 1_000, // 5 min
  /** Recap page auto-refresh (ms). */
  recap: 60 * 60 * 1_000, // 1 hour
  /** Feature flags polling (ms). */
  flags: 5 * 60 * 1_000, // 5 min
} as const;
