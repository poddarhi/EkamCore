import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import {
  ConnectivityManager,
  type ConnectivityState,
} from '../services/ConnectivityManager';

interface ConnectivityCtx {
  state: ConnectivityState;
  isOnline: boolean;
}

const ConnectivityContext = createContext<ConnectivityCtx>({
  state: 'CONNECTED',
  isOnline: true,
});

export function ConnectivityProvider({children}: {children: ReactNode}) {
  const [state, setState] = useState<ConnectivityState>(
    ConnectivityManager.getState(),
  );

  useEffect(() => {
    ConnectivityManager.start();
    const unsub = ConnectivityManager.subscribe(setState);
    return () => {
      unsub();
      ConnectivityManager.stop();
    };
  }, []);

  const isOnline = state === 'CONNECTED' || state === 'DEGRADED';

  return (
    <ConnectivityContext.Provider value={{state, isOnline}}>
      {children}
    </ConnectivityContext.Provider>
  );
}

export function useConnectivity(): ConnectivityCtx {
  return useContext(ConnectivityContext);
}
