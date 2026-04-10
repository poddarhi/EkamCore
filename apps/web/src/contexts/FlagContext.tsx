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
  people_enabled: false,
  photos_enabled: true,
  files_enabled: true,
  settings_enabled: true,
};

export function FlagProvider({ children }: { children: ReactNode }) {
  const flags = useMemo(() => PHASE_0_FLAGS, []);
  return <FlagContext.Provider value={flags}>{children}</FlagContext.Provider>;
}

export function useFlags(): Flags {
  return useContext(FlagContext);
}

export function useFlag(key: string): boolean {
  const flags = useFlags();
  return flags[key] ?? false;
}
