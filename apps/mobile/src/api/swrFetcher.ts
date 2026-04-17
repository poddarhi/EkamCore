/**
 * SWR fetcher with cache-first strategy (S16-003).
 *
 * Pattern:
 * 1. Check CacheManager for fresh entry → return immediately if fresh
 * 2. Fire API fetch (if online)
 * 3. On success → update cache + return fresh data
 * 4. On failure → return stale cache (if any) with isStale=true
 * 5. No cache + no network → throw
 *
 * Usage with SWR:
 *   const { data, error } = useSWR(key, (k) => cachedFetch(k, fetchFn, opts))
 */

import {cacheManager, type CacheEntry, type CacheType} from '../services/CacheManager';
import {CACHE_TTL, cacheKey} from '../services/cacheConfig';
import {ConnectivityManager} from '../services/ConnectivityManager';

export interface CachedFetchOptions {
  /** Cache type for TTL lookup and cache key prefix. */
  cacheType: CacheType;
  /** Cache key identifier (appended to type prefix). */
  cacheId: string;
  /** Override TTL in seconds (defaults to CACHE_TTL[cacheType]). */
  ttlSeconds?: number;
}

export interface CachedResult<T> {
  data: T;
  isStale: boolean;
  fromCache: boolean;
  fetchedAt: number;
}

/**
 * Fetch with cache-first strategy.
 *
 * @param fetchFn  The API fetch function (e.g. () => todayApi.getToday())
 * @param opts     Cache type + key configuration
 */
export async function cachedFetch<T>(
  fetchFn: () => Promise<T>,
  opts: CachedFetchOptions,
): Promise<CachedResult<T>> {
  const key = cacheKey(opts.cacheType, opts.cacheId);
  const ttl = opts.ttlSeconds ?? CACHE_TTL[opts.cacheType];

  // 1. Check cache
  const cached = await cacheManager.get<T>(key);
  if (cached && !cached.isStale) {
    return {
      data: cached.value,
      isStale: false,
      fromCache: true,
      fetchedAt: cached.fetchedAt,
    };
  }

  // 2. Try API fetch
  const connState = ConnectivityManager.getState();
  const isOnline =
    connState === 'CONNECTED' || connState === 'DEGRADED';

  if (isOnline) {
    try {
      const data = await fetchFn();

      // 3. Update cache on success
      await cacheManager.set(key, data, ttl, opts.cacheType);

      return {
        data,
        isStale: false,
        fromCache: false,
        fetchedAt: Date.now(),
      };
    } catch (fetchError) {
      // Fetch failed — fall through to stale cache
      if (cached) {
        return {
          data: cached.value,
          isStale: true,
          fromCache: true,
          fetchedAt: cached.fetchedAt,
        };
      }
      throw fetchError;
    }
  }

  // 4. Offline — return stale cache if available
  if (cached) {
    return {
      data: cached.value,
      isStale: true,
      fromCache: true,
      fetchedAt: cached.fetchedAt,
    };
  }

  // 5. No cache + no network
  throw new Error(
    `No cached data for ${key} and device is offline (${connState}).`,
  );
}
