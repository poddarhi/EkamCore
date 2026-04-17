/**
 * useRecapQuery — fetches Recap cards with cache-first strategy (S16-004).
 */
import {useCallback, useEffect, useState} from 'react';
import {cachedFetch, type CachedResult} from '../api/swrFetcher';
import * as recapApi from '../api/endpoints/recap';
import type {ResponseEnvelope} from '../types/cards';
import type {RecapPeriod} from '../types/api';
import {REFRESH_INTERVALS} from '../config/api';

interface RecapQueryResult {
  data: ResponseEnvelope | null;
  isLoading: boolean;
  isStale: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
}

export function useRecapQuery(
  period: RecapPeriod = 'daily',
  date?: string,
): RecapQueryResult {
  const [result, setResult] = useState<CachedResult<ResponseEnvelope> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await cachedFetch(
        () => recapApi.getRecap(period, date),
        {
          cacheType: 'recap',
          cacheId: `${period}:${date ?? 'latest'}`,
        },
      );
      setResult(res);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, [period, date]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVALS.recap);
    return () => clearInterval(interval);
  }, [fetchData]);

  return {
    data: result?.data ?? null,
    isLoading,
    isStale: result?.isStale ?? false,
    error,
    refresh: fetchData,
  };
}
