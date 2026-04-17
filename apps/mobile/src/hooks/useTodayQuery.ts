/**
 * useTodayQuery — fetches Today cards with cache-first SWR strategy (S16-004).
 */
import {useCallback, useEffect, useState} from 'react';
import {cachedFetch, type CachedResult} from '../api/swrFetcher';
import * as todayApi from '../api/endpoints/today';
import type {ResponseEnvelope} from '../types/cards';
import {REFRESH_INTERVALS} from '../config/api';

interface TodayQueryResult {
  data: ResponseEnvelope | null;
  isLoading: boolean;
  isStale: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
}

export function useTodayQuery(date?: string): TodayQueryResult {
  const [result, setResult] = useState<CachedResult<ResponseEnvelope> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await cachedFetch(
        () => todayApi.getToday(date),
        {cacheType: 'today', cacheId: date ?? 'current'},
      );
      setResult(res);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, [date]);

  useEffect(() => {
    fetchData();
    // Auto-refresh interval
    const interval = setInterval(fetchData, REFRESH_INTERVALS.today);
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
