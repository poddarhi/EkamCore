/**
 * AuthService — stateless auth operations for the mobile client.
 *
 * Mirrors the web AuthContext API but as a plain service class (no React
 * dependency).  Used by AuthContext internally and can be called from
 * background tasks / push notification handlers.
 *
 * Token lifecycle:
 *   Access token  → in-memory only (api/client.ts setAccessToken)
 *   Refresh token → iOS Keychain via TokenManager
 */

import {
  apiFetch,
  setAccessToken,
  getAccessToken,
  getTokenExp,
} from '../api/client';
import {TokenManager} from './TokenManager';

export interface AuthUser {
  id: string;
  role: string;
  workspaceIds: string[];
}

export interface LoginResult {
  user: AuthUser;
  accessToken: string;
}

/** Decode JWT payload without verification. */
function decodeJwt(token: string): Record<string, unknown> {
  const base64 = token.split('.')[1];
  const decoded = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
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

export const AuthService = {
  /**
   * Login with email/password.
   * Stores access token in memory, refresh token in Keychain.
   */
  async login(email: string, password: string): Promise<LoginResult> {
    const data = await apiFetch<{
      access_token: string;
      refresh_token?: string;
    }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({email, password}),
    });

    setAccessToken(data.access_token);

    if (data.refresh_token) {
      await TokenManager.saveRefreshToken(data.refresh_token);
    }

    return {
      user: userFromToken(data.access_token),
      accessToken: data.access_token,
    };
  },

  /**
   * Silent refresh using stored refresh token.
   * Returns the new user if successful, null otherwise.
   */
  async refresh(): Promise<AuthUser | null> {
    const refreshToken = await TokenManager.loadRefreshToken();
    if (!refreshToken) return null;

    try {
      const data = await apiFetch<{access_token: string}>(
        '/auth/refresh',
        {
          method: 'POST',
          headers: {Authorization: `Bearer ${refreshToken}`},
        },
      );
      setAccessToken(data.access_token);
      return userFromToken(data.access_token);
    } catch {
      setAccessToken(null);
      return null;
    }
  },

  /**
   * Logout: call API, clear all tokens.
   */
  async logout(): Promise<void> {
    try {
      await apiFetch('/auth/logout', {method: 'POST'});
    } catch {
      // Best-effort — clear local state regardless
    } finally {
      setAccessToken(null);
      await TokenManager.clearRefreshToken();
    }
  },

  /**
   * Check if the current access token needs refreshing.
   * Returns true if token expires within the given margin (ms).
   */
  needsRefresh(marginMs: number = 60_000): boolean {
    const token = getAccessToken();
    if (!token) return true;

    const exp = getTokenExp(token);
    if (!exp) return true;

    return exp * 1000 - Date.now() < marginMs;
  },

  /**
   * Get the current user from the in-memory access token.
   * Returns null if no token is set.
   */
  getCurrentUser(): AuthUser | null {
    const token = getAccessToken();
    if (!token) return null;
    try {
      return userFromToken(token);
    } catch {
      return null;
    }
  },
};
