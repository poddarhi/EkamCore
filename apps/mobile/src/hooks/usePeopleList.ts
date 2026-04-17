/**
 * usePeopleList — fetches people with search and pagination (S16-006).
 */
import {useCallback, useEffect, useState} from 'react';
import * as peopleApi from '../api/endpoints/people';
import type {Person} from '../api/endpoints/people';

interface PeopleListResult {
  people: Person[];
  isLoading: boolean;
  error: Error | null;
  nextCursor: string | null;
  refresh: () => Promise<void>;
  loadMore: () => Promise<void>;
}

export function usePeopleList(search?: string): PeopleListResult {
  const [people, setPeople] = useState<Person[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await peopleApi.listPeople(undefined, 50, search);
      setPeople(res.items);
      setNextCursor(res.next_cursor);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, [search]);

  const loadMore = useCallback(async () => {
    if (!nextCursor) return;
    try {
      const res = await peopleApi.listPeople(nextCursor, 50, search);
      setPeople(prev => [...prev, ...res.items]);
      setNextCursor(res.next_cursor);
    } catch {
      // Silent fail on load more
    }
  }, [nextCursor, search]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {people, isLoading, error, nextCursor, refresh: fetchData, loadMore};
}
