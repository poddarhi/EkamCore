/**
 * useReviewQueue — fetches and manages the face cluster review queue (S16-006).
 */
import {useCallback, useEffect, useState} from 'react';
import * as peopleApi from '../api/endpoints/people';
import type {ReviewCluster} from '../api/endpoints/people';

interface ReviewQueueResult {
  clusters: ReviewCluster[];
  currentIndex: number;
  total: number;
  isLoading: boolean;
  error: Error | null;
  confirm: (personId: string) => Promise<void>;
  reject: () => Promise<void>;
  skip: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useReviewQueue(): ReviewQueueResult {
  const [clusters, setClusters] = useState<ReviewCluster[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchQueue = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await peopleApi.getReviewQueue();
      setClusters(res.items);
      setTotal(res.total);
      setCurrentIndex(0);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const current = clusters[currentIndex] ?? null;

  const advance = useCallback(() => {
    setClusters(prev => prev.filter((_, i) => i !== currentIndex));
    // currentIndex stays the same; the next item slides into position
  }, [currentIndex]);

  const confirm = useCallback(
    async (personId: string) => {
      if (!current) return;
      await peopleApi.confirmCluster(current.id, personId);
      advance();
    },
    [current, advance],
  );

  const reject = useCallback(async () => {
    if (!current) return;
    await peopleApi.rejectCluster(current.id);
    advance();
  }, [current, advance]);

  const skip = useCallback(async () => {
    if (!current) return;
    await peopleApi.skipCluster(current.id);
    advance();
  }, [current, advance]);

  return {
    clusters,
    currentIndex,
    total,
    isLoading,
    error,
    confirm,
    reject,
    skip,
    refresh: fetchQueue,
  };
}
