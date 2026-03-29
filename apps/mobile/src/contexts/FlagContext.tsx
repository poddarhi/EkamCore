/**
 * Feature flag context — fetches from GET /api/v1/flags on mount and every 5min.
 * Falls back to Phase 0 hardcoded defaults when offline or before first fetch.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {apiFetch} from '../api/client';

interface FlagState {
  flags: Record<string, boolean>;
  currentPhase: number;
  useFlag: (key: string) => boolean;
}

/** Phase 0 defaults — all advanced features off. */
const PHASE0_FLAGS: Record<string, boolean> = {
  'today.enabled': true,
  'recap.enabled': false,
  'search.enabled': false,
  'people.enabled': false,
  'settings.enabled': true,
  'face-clustering.enabled': false,
  'llm-query.enabled': false,
  'write-through.enabled': false,
};

const FlagContext = createContext<FlagState>({
  flags: PHASE0_FLAGS,
  currentPhase: 0,
  useFlag: (key: string) => PHASE0_FLAGS[key] ?? false,
});

const REFRESH_INTERVAL_MS = 5 * 60 * 1_000;

export function FlagProvider({children}: {children: ReactNode}) {
  const [flags, setFlags] = useState<Record<string, boolean>>(PHASE0_FLAGS);
  const [currentPhase, setCurrentPhase] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchFlags = useCallback(async () => {
    try {
      const data = await apiFetch<{
        flags: Record<string, boolean>;
        current_phase: number;
      }>('/flags');
      setFlags(data.flags);
      setCurrentPhase(data.current_phase);
    } catch {
      // Offline — keep current (or default) flags
    }
  }, []);

  useEffect(() => {
    void fetchFlags();
    timerRef.current = setInterval(() => void fetchFlags(), REFRESH_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchFlags]);

  const useFlag = useCallback(
    (key: string) => flags[key] ?? false,
    [flags],
  );

  return (
    <FlagContext.Provider value={{flags, currentPhase, useFlag}}>
      {children}
    </FlagContext.Provider>
  );
}

export function useFlags(): FlagState {
  return useContext(FlagContext);
}
