/**
 * Today endpoint functions (S16-001).
 */

import {apiClient} from '../ApiClient';
import type {ResponseEnvelope} from '../../types/cards';

export async function getToday(date?: string): Promise<ResponseEnvelope> {
  const params = date ? `?date=${date}` : '';
  return apiClient.request<ResponseEnvelope>({
    path: `/today${params}`,
  });
}
