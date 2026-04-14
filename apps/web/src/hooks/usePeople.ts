/**
 * SWR hooks for the People Graph surfaces (S13-001).
 *
 * Cache keys are the exact URL — SWR dedupes by string equality and
 * the fetch wrapper scopes every request to the caller's workspace
 * via the auth cookie, so we don't need a workspace_id in the key.
 */

import useSWR, { type SWRConfiguration } from "swr";

import { swrFetcher } from "../api/client";
import type { ListPeopleParams } from "../api/people";
import type { ListReviewQueueParams } from "../api/review_queue";
import type {
  PaginatedOperations,
  PaginatedPersons,
  PaginatedReviewItems,
  ReviewQueueDetail,
  TrustedPerson,
} from "../types/people";

function toQuery(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  const qs = new URLSearchParams();
  for (const [k, v] of entries) qs.set(k, String(v));
  return `?${qs.toString()}`;
}

export function usePeopleList(
  params: ListPeopleParams = {},
  config?: SWRConfiguration,
) {
  const key = `/api/v1/people${toQuery(params)}`;
  return useSWR<PaginatedPersons>(key, swrFetcher, config);
}

export function usePerson(personId: string | null | undefined, config?: SWRConfiguration) {
  const key = personId ? `/api/v1/people/${personId}` : null;
  return useSWR<TrustedPerson>(key, swrFetcher, config);
}

export function usePersonOperations(limit = 50, config?: SWRConfiguration) {
  const key = `/api/v1/people/operations${toQuery({ limit })}`;
  return useSWR<PaginatedOperations>(key, swrFetcher, config);
}

export function useReviewQueue(
  params: ListReviewQueueParams = {},
  config?: SWRConfiguration,
) {
  const key = `/api/v1/review-queue${toQuery(params)}`;
  return useSWR<PaginatedReviewItems>(key, swrFetcher, config);
}

export function useReviewQueueItem(
  clusterId: string | null | undefined,
  config?: SWRConfiguration,
) {
  const key = clusterId ? `/api/v1/review-queue/${clusterId}` : null;
  return useSWR<ReviewQueueDetail>(key, swrFetcher, config);
}

/** Sidebar badge count. Reads up to 100 pending items, returns the
 * length; caller can cap the display at "99+". Fails open (0) when
 * consent is not active so the sidebar doesn't flash an error badge. */
export function useReviewQueueBadge() {
  const { data, error } = useSWR<PaginatedReviewItems>(
    "/api/v1/review-queue?limit=100",
    swrFetcher,
    { shouldRetryOnError: false },
  );
  if (error) return 0;
  return data?.items.length ?? 0;
}

/** Face consent state for the current workspace. Used by the sidebar
 * People entry to decide between enabled / disabled + tooltip. */
export interface FaceConsentState {
  accepted: boolean;
  loading: boolean;
}

export function useFaceConsent(): FaceConsentState {
  const { data, error, isLoading } = useSWR<{ accepted: boolean }>(
    "/api/v1/settings/face-clustering/consent",
    swrFetcher,
    { shouldRetryOnError: false },
  );
  if (error) return { accepted: false, loading: false };
  return { accepted: data?.accepted ?? false, loading: isLoading };
}
