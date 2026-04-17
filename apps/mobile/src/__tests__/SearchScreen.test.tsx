import React from 'react';
import {render, screen, fireEvent} from '@testing-library/react-native';
import {SearchScreen} from '../screens/SearchScreen';

// Mock connectivity
jest.mock('../contexts/ConnectivityContext', () => ({
  ConnectivityProvider: ({children}: {children: React.ReactNode}) => children,
  useConnectivity: jest.fn().mockReturnValue({state: 'CONNECTED', isOnline: true}),
}));

// Mock ConnectivityBanner
jest.mock('../components/ConnectivityBanner', () => ({
  ConnectivityBanner: () => null,
}));

// Mock ApiClient
jest.mock('../api/ApiClient', () => ({
  apiClient: {
    request: jest.fn().mockResolvedValue({cards: [], answer_text: null}),
    setBaseUrl: jest.fn(),
    setAuthToken: jest.fn(),
    getBaseUrl: jest.fn().mockReturnValue('https://test.local/api/v1'),
    clearAuth: jest.fn(),
    setOnAuthFailure: jest.fn(),
  },
  ApiError: class extends Error {
    status: number;
    errorCode: string;
    constructor(s: number, c: string, m: string) {
      super(m);
      this.status = s;
      this.errorCode = c;
    }
  },
}));

// Mock swrFetcher
jest.mock('../api/swrFetcher', () => ({
  cachedFetch: jest.fn().mockResolvedValue({data: {data: []}, isStale: false, fromCache: false, fetchedAt: Date.now()}),
}));

// Mock search endpoint
jest.mock('../api/endpoints/search', () => ({
  search: jest.fn().mockResolvedValue({data: [], facets: {}, pagination: {cursor: 0, has_more: false}}),
}));

describe('SearchScreen', () => {
  it('renders search input and filter chips', () => {
    render(<SearchScreen />);
    expect(screen.getByAccessibilityLabel('Search')).toBeTruthy();
    expect(screen.getByText('All')).toBeTruthy();
    expect(screen.getByText('Events')).toBeTruthy();
    expect(screen.getByText('Files')).toBeTruthy();
    expect(screen.getByText('Photos')).toBeTruthy();
  });

  it('shows initial empty state before search', () => {
    render(<SearchScreen />);
    expect(screen.getByText('Search across everything')).toBeTruthy();
  });

  it('has a clear button when text is entered', () => {
    render(<SearchScreen />);
    const input = screen.getByAccessibilityLabel('Search');
    fireEvent.changeText(input, 'meeting');
    expect(screen.getByAccessibilityLabel('Clear search')).toBeTruthy();
  });
});
