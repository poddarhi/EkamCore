/**
 * API endpoint type definitions for the mobile client.
 *
 * Request/response shapes for each endpoint the mobile app calls.
 */

// ── Auth ──

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
}

export interface RefreshResponse {
  access_token: string;
}

// ── Today ──

// Request is a query parameter: workspace_id (UUID string)
// Response is ResponseEnvelope (see cards.ts)

// ── Recap ──

export type RecapPeriod = 'daily' | 'weekly';

export interface RecapParams {
  workspace_id: string;
  period?: RecapPeriod;
  date?: string; // YYYY-MM-DD
}

// Response is ResponseEnvelope (see cards.ts)

// ── Health ──

export interface HealthResponse {
  status: 'ok' | 'degraded';
  postgres: boolean;
  redis: boolean;
  qdrant: boolean;
}

// ── Feature Flags ──

export interface FlagsResponse {
  flags: Record<string, boolean>;
}

// ── Error shape (from API error responses) ──

export interface ApiErrorBody {
  error_code: string;
  message: string;
  correlation_id?: string;
  details?: Record<string, unknown>;
}

// ── Search ──

// Request/response types live in search.ts — this section only adds the
// endpoint constant.  See src/types/search.ts for SearchRequest, SearchResponse,
// SearchFilters, and CachedSearchResult.

// ── Endpoint paths (for type-safe routing) ──

export const ENDPOINTS = {
  AUTH_LOGIN: '/auth/login',
  AUTH_REFRESH: '/auth/refresh',
  AUTH_LOGOUT: '/auth/logout',
  TODAY: '/today',
  RECAP: '/recap',
  SEARCH: '/search',
  HEALTH: '/health',
  FLAGS: '/flags',
} as const;
