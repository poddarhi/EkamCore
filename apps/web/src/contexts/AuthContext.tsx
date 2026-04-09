import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  apiFetch,
  ApiError,
  setAccessToken,
  getTokenExp,
  registerAuthCallbacks,
  unregisterAuthCallbacks,
} from "../api/client";

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
  refresh: () => Promise<boolean>;
}

const AuthContext = createContext<AuthState | null>(null);

function decodeJwtPayload(token: string): Record<string, unknown> {
  const base64 = token.split(".")[1];
  return JSON.parse(atob(base64));
}

function userFromToken(token: string): User {
  const payload = decodeJwtPayload(token);
  return {
    id: payload.sub as string,
    role: (payload.role as string) ?? "standard",
    workspaceIds: (payload.workspaces as string[]) ?? [],
  };
}

/** How many ms before expiry to trigger a refresh (1 minute). */
const REFRESH_MARGIN_MS = 60_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Schedule proactive refresh ──
  const scheduleRefresh = useCallback((token: string, doRefresh: () => Promise<boolean>) => {
    // Clear any existing timer
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    const exp = getTokenExp(token);
    if (!exp) return;

    const expiresInMs = exp * 1000 - Date.now();
    const refreshInMs = expiresInMs - REFRESH_MARGIN_MS;

    if (refreshInMs <= 0) {
      // Token is already (nearly) expired — refresh now
      doRefresh();
      return;
    }

    refreshTimerRef.current = setTimeout(() => {
      doRefresh();
    }, refreshInMs);
  }, []);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  // ── Core refresh ──
  const refresh = useCallback(async (): Promise<boolean> => {
    try {
      const data = await apiFetch<{ access_token: string }>(
        "/api/v1/auth/refresh",
        { method: "POST" },
      );
      setAccessToken(data.access_token);
      setUser(userFromToken(data.access_token));
      scheduleRefresh(data.access_token, refresh);
      return true;
    } catch {
      setAccessToken(null);
      setUser(null);
      clearRefreshTimer();
      return false;
    }
  }, [scheduleRefresh, clearRefreshTimer]);

  // ── Register client callbacks for 401-triggered refreshes ──
  useEffect(() => {
    registerAuthCallbacks(
      // onTokenRefreshed: client.ts got a new token via 401 retry
      (token: string) => {
        setUser(userFromToken(token));
        scheduleRefresh(token, refresh);
      },
      // onRefreshFailed: 401 retry refresh failed → force logout
      () => {
        setAccessToken(null);
        setUser(null);
        clearRefreshTimer();
      },
    );
    return () => unregisterAuthCallbacks();
  }, [scheduleRefresh, clearRefreshTimer, refresh]);

  // ── Silent refresh on mount ──
  useEffect(() => {
    refresh().finally(() => setIsLoading(false));
  }, [refresh]);

  // ── Cleanup timer on unmount ──
  useEffect(() => {
    return () => clearRefreshTimer();
  }, [clearRefreshTimer]);

  // ── Login ──
  const login = useCallback(async (email: string, password: string) => {
    const data = await apiFetch<{ access_token: string }>(
      "/api/v1/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
    );
    setAccessToken(data.access_token);
    setUser(userFromToken(data.access_token));
    scheduleRefresh(data.access_token, refresh);
  }, [scheduleRefresh, refresh]);

  // ── Logout ──
  const logout = useCallback(async () => {
    clearRefreshTimer();
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) {
        console.warn("Logout request failed", e);
      }
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, [clearRefreshTimer]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      isAuthenticated: !!user,
      isLoading,
      login,
      logout,
      refresh,
    }),
    [user, isLoading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
