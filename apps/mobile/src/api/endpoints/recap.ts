/**
 * Recap endpoint functions (S16-001).
 */

import {apiClient} from '../ApiClient';
import type {ResponseEnvelope} from '../../types/cards';
import type {RecapPeriod} from '../../types/api';

export async function getRecap(
  period: RecapPeriod = 'daily',
  date?: string,
): Promise<ResponseEnvelope> {
  const params = new URLSearchParams();
  params.set('period', period);
  if (date) params.set('date', date);
  return apiClient.request<ResponseEnvelope>({
    path: `/recap?${params.toString()}`,
  });
}
