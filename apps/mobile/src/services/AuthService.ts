/**
 * AuthService — authentication operations for the mobile client (S16-002).
 *
 * Uses ApiClient (S16-001) for HTTP requests and TokenManager for secure
 * token storage. Provides biometric unlock flow.
 *
 * Token lifecycle:
 *   Access token  → in-memory only (ApiClient + TokenManager)
 *   Refresh token → iOS/Android Keychain with biometric protection
 */

import {apiClient, ApiError} from '../api/ApiClient';
import {TokenManager} from './TokenManager';

// ── Types ───────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  role: string;
  workspaceIds: string[];
}

export interface LoginResult {
  user: AuthUser;
  accessToken: string;
}

// ── JWT decode (no verification — server-trusted) ───────────────────────────

function decodeJwt(token: string): Record<string, unknown> {
  const base64 = token.split('.')[1];
  // React Native has atob via polyfill or hermes; fallback to manual decode
  let decoded: string;
  try {
    // atob is available in Hermes (RN runtime) but not in Node typings
    const _atob = (globalThis as unknown as {atob?: (s: string) => string}).atob;
    if (!_atob) throw new Error('no atob');
    decoded = _atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
  } catch {
    // Manual base64 decode fallback
    const chars =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
    const str = base64.replace(/-/g, '+').replace(/_/g, '/');
    let output = '';
    for (let i = 0; i < str.length; i += 4) {
      const a = chars.indexOf(str[i]);
      const b = chars.indexOf(str[i + 1]);
      const c = chars.indexOf(str[i + 2]);
      const d = chars.indexOf(str[i + 3]);
      output += String.fromCharCode((a << 2) | (b >> 4));
      if (c !== 64) output += String.fromCharCode(((b & 15) << 4) | (c >> 2));
      if (d !== 64) output += String.fromCharCode(((c & 3) << 6) | d);
    }
    decoded = output;
  }
  return JSON.parse(decoded);
}

function userFromToken(token: string): AuthUser {
  const payload = decodeJwt(token);
  return {
    id: payload.sub as string,
    role: (payload.role as string) ?? 'standard',
    workspaceIds: (payload.workspaces as string[]) ?? [],
  };
}

// ── Service ─────────────────────────────────────────────────────────────────

export const AuthService = {
  /**
   * Login with email/password.
   * Stores access token in memory, refresh token in Keychain (biometric-protected).
   */
  async login(email: string, password: string): Promise<LoginResult> {
    const data = await apiClient.request<{
      access_token: string;
      refresh_token?: string;
    }>({
      path: '/auth/login',
      method: 'POST',
      body: {email, password},
      noRetry: true,
    });

    // Store tokens
    TokenManager.setAccessToken(data.access_token);
    apiClient.setAuthToken(data.access_token);

    if (data.refresh_token) {
      await TokenManager.setTokens(data.access_token, data.refresh_token);
    }

    return {
      user: userFromToken(data.access_token),
      accessToken: data.access_token,
    };
  },

  /**
   * Silent refresh using stored refresh token.
   * Triggers biometric prompt to access Keychain-protected refresh token.
   * Returns the new user if successful, null otherwise.
   */
  async refresh(): Promise<AuthUser | null> {
    const refreshToken = await TokenManager.getRefreshToken();
    if (!refreshToken) return null;

    try {
      const data = await apiClient.request<{
        access_token: string;
        refresh_token?: string;
      }>({
        path: '/auth/refresh',
        method: 'POST',
        headers: {Authorization: `Bearer ${refreshToken}`},
        noRetry: true,
      });

      TokenManager.setAccessToken(data.access_token);
      apiClient.setAuthToken(data.access_token);

      // Rotate refresh token if server provides a new one
      if (data.refresh_token) {
        await TokenManager.setTokens(data.access_token, data.refresh_token);
      }

      return userFromToken(data.access_token);
    } catch {
      // Refresh failed — clear everything
      TokenManager.setAccessToken(null);
      apiClient.clearAuth();
      return null;
    }
  },

  /**
   * Biometric unlock flow — called on app launch when stored refresh exists.
   *
   * 1. Check hasStoredRefresh (no biometric prompt)
   * 2. If yes, call getRefreshToken (triggers biometric)
   * 3. If biometric succeeds, refresh access token
   * 4. If user cancels or fails, return null (show login screen)
   */
  async unlockWithBiometric(): Promise<AuthUser | null> {
    const hasStored = await TokenManager.hasStoredRefresh();
    if (!hasStored) return null;

    // This triggers the biometric prompt via getRefreshToken()
    return AuthService.refresh();
  },

  /**
   * Logout: revoke session, clear all tokens and cache.
   */
  async logout(): Promise<void> {
    try {
      await apiClient.request({
        path: '/auth/logout',
        method: 'POST',
        noRetry: true,
      });
    } catch {
      // Best-effort — clear local state regardless
    } finally {
      TokenManager.setAccessToken(null);
      apiClient.clearAuth();
      await TokenManager.clearTokens();
      // S16-003: Secure wipe of all cached data on logout (FS-178)
      try {
        const {cacheManager} = await import('./CacheManager');
        await cacheManager.wipeAll();
      } catch {
        // Cache wipe is best-effort — may not be initialized
      }
    }
  },

  /**
   * Check if biometric unlock is available on this device.
   */
  async getBiometricType() {
    return TokenManager.getBiometricType();
  },

  /**
   * Check if the current access token needs refreshing.
   * Returns true if token expires within the given margin (ms).
   */
  needsRefresh(marginMs: number = 60_000): boolean {
    const token = TokenManager.getAccessToken();
    if (!token) return true;

    try {
      const payload = decodeJwt(token);
      const exp = payload.exp as number | undefined;
      if (!exp) return true;
      return exp * 1000 - Date.now() < marginMs;
    } catch {
      return true;
    }
  },

  /**
   * Get the current user from the in-memory access token.
   * Returns null if no token is set.
   */
  getCurrentUser(): AuthUser | null {
    const token = TokenManager.getAccessToken();
    if (!token) return null;
    try {
      return userFromToken(token);
    } catch {
      return null;
    }
  },
};
