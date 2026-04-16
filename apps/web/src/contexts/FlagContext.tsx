import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from "react";

type Flags = Record<string, boolean>;

const FlagContext = createContext<Flags>({});

/** Phase 0 hardcoded flags. Will be replaced with API fetch later. */
const PHASE_0_FLAGS: Flags = {
  auth_enabled: true,
  today_enabled: true,
  recap_enabled: true,
  search_enabled: true,
  people_enabled: true,
  // S13-001: Phase 3 face-clustering feature flag. Pages under /people
  // gate on this. Flip to false to disable the People UI even when
  // face consent is active (e.g. kill switch).
  face_clustering_enabled: true,
  photos_enabled: true,
  files_enabled: true,
  settings_enabled: true,
};

export function FlagProvider({
  children,
  overrides,
}: {
  children: ReactNode;
  overrides?: Flags;
}) {
  const flags = useMemo(
    () => (overrides ? { ...PHASE_0_FLAGS, ...overrides } : PHASE_0_FLAGS),
    [overrides],
  );
  return <FlagContext.Provider value={flags}>{children}</FlagContext.Provider>;
}

export function useFlags(): Flags {
  return useContext(FlagContext);
}

export function useFlag(key: string): boolean {
  const flags = useFlags();
  return flags[key] ?? false;
}
