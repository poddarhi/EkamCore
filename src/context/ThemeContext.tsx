import React, { createContext, useContext, useMemo } from 'react';
import { lightColors, type ThemeColors } from '../theme';

interface ThemeState {
  colors: ThemeColors;
  scheme: 'light';
}

const ThemeContext = createContext<ThemeState | null>(null);

// The app is light-mode only.
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const value = useMemo<ThemeState>(
    () => ({ colors: lightColors, scheme: 'light' }),
    [],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return ctx;
}
