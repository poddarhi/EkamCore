import React from 'react';
import {render, screen} from '@testing-library/react-native';
import {SettingsScreen} from '../screens/SettingsScreen';
import {AuthContext} from '../contexts/AuthContext';

// Mock connectivity
jest.mock('../contexts/ConnectivityContext', () => ({
  useConnectivity: jest.fn().mockReturnValue({state: 'CONNECTED', isOnline: true}),
}));
jest.mock('../components/ConnectivityBanner', () => ({
  ConnectivityBanner: () => null,
}));

// Mock CacheManager
jest.mock('../services/CacheManager', () => ({
  cacheManager: {
    getSize: jest.fn().mockResolvedValue(5242880),
    getMaxSize: jest.fn().mockReturnValue(104857600),
    wipeAll: jest.fn().mockResolvedValue(undefined),
  },
}));

// Mock ApiClient
jest.mock('../api/ApiClient', () => ({
  apiClient: {
    request: jest.fn().mockResolvedValue({}),
    getBaseUrl: jest.fn().mockReturnValue('https://test.local/api/v1'),
    setBaseUrl: jest.fn(),
    setAuthToken: jest.fn(),
    clearAuth: jest.fn(),
    setOnAuthFailure: jest.fn(),
  },
  ApiError: class extends Error {},
}));

function renderWithAuth() {
  return render(
    <AuthContext.Provider
      value={{
        user: {id: 'user@test.com', role: 'admin', workspaceIds: ['ws-1']},
        isAuthenticated: true,
        isLoading: false,
        biometricType: 'FaceID' as never,
        biometricAvailable: true,
        login: jest.fn(),
        logout: jest.fn(),
        unlockBiometric: jest.fn(),
      }}>
      <SettingsScreen />
    </AuthContext.Provider>,
  );
}

describe('SettingsScreen', () => {
  it('renders section headers', () => {
    renderWithAuth();
    expect(screen.getByText('Settings')).toBeTruthy();
    expect(screen.getByText('Account')).toBeTruthy();
    expect(screen.getByText('Hub Connection')).toBeTruthy();
    expect(screen.getByText('Cache')).toBeTruthy();
    expect(screen.getByText('About')).toBeTruthy();
  });

  it('renders logout button', () => {
    renderWithAuth();
    expect(screen.getByAccessibilityLabel('Log out')).toBeTruthy();
  });

  it('renders hub URL', () => {
    renderWithAuth();
    expect(screen.getByText('https://test.local/api/v1')).toBeTruthy();
  });
});
