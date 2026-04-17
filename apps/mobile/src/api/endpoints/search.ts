/**
 * Search endpoint functions (S16-001).
 */

import {apiClient} from '../ApiClient';
import type {SearchRequest, SearchResponse} from '../../types/search';

export async function search(params: SearchRequest): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  qs.set('q', params.q);
  if (params.per_page) qs.set('per_page', String(params.per_page));
  if (params.cursor) qs.set('cursor', String(params.cursor));
  if (params.filters?.type && params.filters.type !== 'all') {
    qs.set('type', params.filters.type);
  }
  if (params.filters?.date_from) qs.set('date_from', params.filters.date_from);
  if (params.filters?.date_to) qs.set('date_to', params.filters.date_to);

  return apiClient.request<SearchResponse>({
    path: `/search?${qs.toString()}`,
  });
}
