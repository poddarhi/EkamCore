/**
 * Search type definitions for the mobile client (S09-002).
 *
 * Mirrors GET /api/v1/search query parameters and response shape.
 * Card types are imported from cards.ts — this file only adds
 * search-specific request/response/filter types.
 */

import type { Card, CardType, ResponseMetadata, SourceRef } from './cards';

// ── Type filter (matches backend Literal) ──

export type SearchTypeFilter =
  | 'all'
  | 'calendar'
  | 'reminder'
  | 'contact'
  | 'file'
  | 'photo';

// ── Search filters ──

export interface SearchFilters {
  /** Type filter — defaults to "all". */
  type: SearchTypeFilter;
  /** ISO 8601 date string for event/reminder start. */
  date_from?: string;
  /** ISO 8601 date string for event/reminder end. */
  date_to?: string;
  /** Filter photos with/without GPS coordinates. */
  has_gps?: boolean;
}

// ── Request ──

export interface SearchRequest {
  /** Search query text (1–200 chars). */
  q: string;
  /** Workspace UUID. */
  workspace_id: string;
  /** Results per page (1–100, default 20). */
  per_page?: number;
  /** Offset cursor for pagination (default 0). */
  cursor?: number;
  /** Filters applied to the search. */
  filters?: SearchFilters;
}

// ── Facets (result counts by type) ──

export interface SearchFacets {
  calendar: number;
  reminder: number;
  contact: number;
  file: number;
  photo: number;
}

// ── Pagination ──

export interface SearchPagination {
  cursor: number;
  has_more: boolean;
}

// ── Response ──

export interface SearchResponse {
  /** Typed search result cards sorted by relevance. */
  data: Card[];
  /** Result counts per type. */
  facets: SearchFacets;
  /** Cursor-based pagination metadata. */
  pagination: SearchPagination;
}

// ── Local cache entry (for offline support) ──

export interface CachedSearchResult {
  /** The query that produced this result. */
  query: string;
  /** Filters that were active. */
  filters: SearchFilters;
  /** Cached response data. */
  response: SearchResponse;
  /** When this result was cached (epoch ms). */
  cached_at: number;
}

// Re-export CardType for convenience — consumers can import from
// either cards.ts or search.ts without caring about the split.
export type { Card, CardType, SourceRef };
