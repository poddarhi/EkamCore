/**
 * Auth endpoint functions (S16-001).
 */

import {apiClient} from '../ApiClient';
import type {LoginRequest, LoginResponse, RefreshResponse} from '../../types/api';

export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiClient.request<LoginResponse>({
    path: '/auth/login',
    method: 'POST',
    body: {email, password} satisfies LoginRequest,
    noRetry: true, // Don't retry login — user should see the error immediately
  });
}

export async function refresh(refreshToken: string): Promise<RefreshResponse> {
  return apiClient.request<RefreshResponse>({
    path: '/auth/refresh',
    method: 'POST',
    headers: {Authorization: `Bearer ${refreshToken}`},
    noRetry: true,
  });
}

export async function logout(): Promise<void> {
  return apiClient.request<void>({
    path: '/auth/logout',
    method: 'POST',
    noRetry: true,
  });
}
