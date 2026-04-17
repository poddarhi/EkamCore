/**
 * Cache TTL configuration per data type (S16-003 / FS-177).
 *
 * Values in seconds. Tuned for a local-first app where the hub is usually
 * reachable — short enough to stay fresh, long enough to be useful offline.
 */

import type {CacheType} from './CacheManager';

/** TTL in seconds for each cache type. */
export const CACHE_TTL: Record<CacheType, number> = {
  today: 4 * 3600,           // 4 hours — cards change with calendar events
  recap: 24 * 3600,          // 24 hours — recap is backward-looking, stable
  personProfile: 12 * 3600,  // 12 hours — person details rarely change
  fileList: 12 * 3600,       // 12 hours — file listings
  photoList: 12 * 3600,      // 12 hours — photo galleries
  searchResult: 30 * 60,     // 30 minutes — search results change with new data
  userProfile: 3600,          // 1 hour — user profile and workspace info
  settings: 3600,             // 1 hour — app settings and feature flags
};

/**
 * Build a cache key for a given type and identifier.
 *
 * Convention: "{type}:{identifier}" — e.g. "today:2026-04-17", "search:weather"
 * Prefix-based deletion uses the type prefix.
 */
export function cacheKey(type: CacheType, id: string): string {
  return `${type}:${id}`;
}
