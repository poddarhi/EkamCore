import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  apiFetch,
  setAccessToken,
  registerRefreshCallback,
  ApiError,
} from '../api/client';
import {TokenManager} from '../services/TokenManager';

interface User {
  id: string;
  role: string;
  workspaceIds: string[];
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

function decodeJwtPayload(token: string): Record<string, unknown> {
  const base64 = token.split('.')[1];
  const decoded = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
  return JSON.parse(decoded);
}

function userFromToken(token: string): User {
  const payload = decodeJwtPayload(token);
  return {
    id: payload.sub as string,
    role: (payload.role as string) ?? 'standard',
    workspaceIds: (payload.workspaces as string[]) ?? [],
  };
}

export function AuthProvider({children}: {children: ReactNode}) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async (): Promise<boolean> => {
    try {
      const refreshToken = await TokenManager.loadRefreshToken();
      if (!refreshToken) return false;

      const data = await apiFetch<{access_token: string}>(
        '/auth/refresh',
        {
          method: 'POST',
          headers: {Authorization: `Bearer ${refreshToken}`},
        },
      );
      setAccessToken(data.access_token);
      setUser(userFromToken(data.access_token));
      return true;
    } catch {
      setAccessToken(null);
      setUser(null);
      return false;
    }
  }, []);

  // Register refresh callback so api/client can call it on 401
  useEffect(() => {
    registerRefreshCallback(refresh);
    return () => registerRefreshCallback(null);
  }, [refresh]);

  // Attempt silent refresh on mount
  useEffect(() => {
    refresh().finally(() => setIsLoading(false));
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiFetch<{
      access_token: string;
      refresh_token?: string;
    }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({email, password}),
    });

    setAccessToken(data.access_token);
    setUser(userFromToken(data.access_token));

    if (data.refresh_token) {
      await TokenManager.saveRefreshToken(data.refresh_token);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch('/auth/logout', {method: 'POST'});
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) {
        console.warn('Logout request failed', e);
      }
    } finally {
      setAccessToken(null);
      setUser(null);
      await TokenManager.clearRefreshToken();
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      isAuthenticated: !!user,
      isLoading,
      login,
      logout,
    }),
    [user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
