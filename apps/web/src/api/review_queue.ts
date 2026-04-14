/**
 * Review Queue API client (S13-001 / S12-005 backend).
 */

import type {
  ConfidenceBucket,
  PaginatedReviewItems,
  ReviewQueueDetail,
} from "../types/people";
import { apiFetch } from "./client";

const BASE = "/api/v1/review-queue";

export interface ListReviewQueueParams {
  confidence?: Exclude<ConfidenceBucket, "none">;
  limit?: number;
  cursor?: string;
}

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  const qs = new URLSearchParams();
  for (const [k, v] of entries) qs.set(k, String(v));
  return `?${qs.toString()}`;
}

export const reviewQueueApi = {
  list: (params: ListReviewQueueParams = {}): Promise<PaginatedReviewItems> =>
    apiFetch<PaginatedReviewItems>(`${BASE}${buildQuery(params)}`),

  get: (clusterId: string): Promise<ReviewQueueDetail> =>
    apiFetch<ReviewQueueDetail>(`${BASE}/${clusterId}`),

  skip: (clusterId: string): Promise<void> =>
    apiFetch<void>(`${BASE}/${clusterId}/skip`, { method: "POST" }),
};

export type ReviewQueueApi = typeof reviewQueueApi;
