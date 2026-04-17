/**
 * AuthContext — provides auth state and actions to the app tree (S16-002).
 *
 * On mount:
 *   1. Check if stored refresh token exists (no biometric prompt)
 *   2. If yes: attempt biometric unlock → silent refresh → logged in
 *   3. If no or cancelled: show LoginScreen
 *
 * Wires ApiClient.onAuthFailure to auto-logout on irrecoverable 401.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import {apiClient, ApiError} from '../api/ApiClient';
import {AuthService, type AuthUser} from '../services/AuthService';
import type {BiometricType} from '../services/TokenManager';
import {TokenManager} from '../services/TokenManager';

// ── Context type ────────────────────────────────────────────────────────────

interface AuthState {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  biometricType: BiometricType | null;
  biometricAvailable: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  unlockBiometric: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

// ── Provider ────────────────────────────────────────────────────────────────

export function AuthProvider({children}: {children: ReactNode}) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [biometricType, setBiometricType] = useState<BiometricType | null>(
    null,
  );
  const [hasStoredRefresh, setHasStoredRefresh] = useState(false);

  // ── Wire ApiClient auth failure → logout ──

  useEffect(() => {
    apiClient.setOnAuthFailure(() => {
      setUser(null);
      TokenManager.clearTokens().catch(() => {});
    });
    return () => apiClient.setOnAuthFailure(null);
  }, []);

  // ── Initialize on mount ──

  useEffect(() => {
    let mounted = true;

    async function init() {
      // Check biometric availability
      const bioType = await AuthService.getBiometricType();
      if (mounted) setBiometricType(bioType);

      // Check if we have a stored refresh token
      const hasRefresh = await TokenManager.hasStoredRefresh();
      if (mounted) setHasStoredRefresh(hasRefresh);

      if (hasRefresh) {
        // Attempt biometric unlock → silent refresh
        const refreshedUser = await AuthService.unlockWithBiometric();
        if (mounted) {
          setUser(refreshedUser);
          setIsLoading(false);
        }
      } else {
        if (mounted) setIsLoading(false);
      }
    }

    init();
    return () => {
      mounted = false;
    };
  }, []);

  // ── Actions ──

  const login = useCallback(async (email: string, password: string) => {
    const result = await AuthService.login(email, password);
    setUser(result.user);
    setHasStoredRefresh(true);
  }, []);

  const logout = useCallback(async () => {
    await AuthService.logout();
    setUser(null);
    setHasStoredRefresh(false);
  }, []);

  const unlockBiometric = useCallback(async () => {
    const refreshedUser = await AuthService.unlockWithBiometric();
    if (refreshedUser) {
      setUser(refreshedUser);
    }
  }, []);

  // ── Value ──

  const value = useMemo<AuthState>(
    () => ({
      user,
      isAuthenticated: !!user,
      isLoading,
      biometricType,
      biometricAvailable: biometricType !== null && hasStoredRefresh,
      login,
      logout,
      unlockBiometric,
    }),
    [user, isLoading, biometricType, hasStoredRefresh, login, logout, unlockBiometric],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
