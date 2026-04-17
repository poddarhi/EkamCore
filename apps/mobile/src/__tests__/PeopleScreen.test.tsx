import React from 'react';
import {render, screen} from '@testing-library/react-native';
import {PeopleScreen} from '../screens/PeopleScreen';

// Mock connectivity
jest.mock('../contexts/ConnectivityContext', () => ({
  useConnectivity: jest.fn().mockReturnValue({state: 'CONNECTED', isOnline: true}),
}));
jest.mock('../components/ConnectivityBanner', () => ({
  ConnectivityBanner: () => null,
}));

// Mock usePeopleList hook
jest.mock('../hooks/usePeopleList', () => ({
  usePeopleList: jest.fn().mockReturnValue({
    people: [
      {id: 'p1', display_name: 'Alice Smith', trust_source: 'face_cluster', face_count: 12, confirmed_at: '2026-04-17'},
      {id: 'p2', display_name: 'Bob Jones', trust_source: 'contact', face_count: 5, confirmed_at: null},
    ],
    isLoading: false,
    error: null,
    nextCursor: null,
    refresh: jest.fn(),
    loadMore: jest.fn(),
  }),
}));

describe('PeopleScreen', () => {
  it('renders people list with names', () => {
    render(<PeopleScreen />);
    expect(screen.getByText('Alice Smith')).toBeTruthy();
    expect(screen.getByText('Bob Jones')).toBeTruthy();
  });

  it('renders search input', () => {
    render(<PeopleScreen />);
    expect(screen.getByAccessibilityLabel('Search people')).toBeTruthy();
  });

  it('renders heading', () => {
    render(<PeopleScreen />);
    expect(screen.getByText('People')).toBeTruthy();
  });
});
