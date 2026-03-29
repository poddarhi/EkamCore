import React from 'react';
import {AuthProvider} from './contexts/AuthContext';
import {FlagProvider} from './contexts/FlagContext';
import {ConnectivityProvider} from './contexts/ConnectivityContext';
import {MainNavigator} from './navigation/MainNavigator';

export default function App() {
  return (
    <ConnectivityProvider>
      <AuthProvider>
        <FlagProvider>
          <MainNavigator />
        </FlagProvider>
      </AuthProvider>
    </ConnectivityProvider>
  );
}
