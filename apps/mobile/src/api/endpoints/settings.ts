/**
 * Settings endpoint functions (S16-001).
 */

import {apiClient} from '../ApiClient';
import type {FlagsResponse, HealthResponse} from '../../types/api';

export async function getSettings(): Promise<Record<string, unknown>> {
  return apiClient.request<Record<string, unknown>>({
    path: '/settings',
  });
}

export async function updateSetting(
  key: string,
  value: unknown,
): Promise<void> {
  return apiClient.request<void>({
    path: '/settings',
    method: 'PATCH',
    body: {[key]: value},
  });
}

export async function getFlags(): Promise<FlagsResponse> {
  return apiClient.request<FlagsResponse>({
    path: '/flags',
  });
}

export async function getHealth(): Promise<HealthResponse> {
  return apiClient.request<HealthResponse>({
    path: '/health',
    noRetry: true,
  });
}
