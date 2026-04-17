import React from 'react';
import {render, screen} from '@testing-library/react-native';
import {TodayScreen} from '../screens/TodayScreen';

// Mock connectivity context
jest.mock('../contexts/ConnectivityContext', () => ({
  ConnectivityProvider: ({children}: {children: React.ReactNode}) => children,
  useConnectivity: jest.fn().mockReturnValue({state: 'CONNECTED', isOnline: true}),
}));

// Mock the today query hook
jest.mock('../hooks/useTodayQuery', () => ({
  useTodayQuery: jest.fn().mockReturnValue({
    data: {
      cards: [
        {
          id: 'status-1',
          type: 'status',
          priority_score: 1,
          source_ids: [],
          payload: {date: '2026-04-17', time_of_day: 'morning', weekday: 'Thursday'},
        },
        {
          id: 'event-1',
          type: 'event',
          priority_score: 0.9,
          source_ids: [],
          payload: {
            title: 'Morning Meeting',
            start_at: '2026-04-17T09:00:00Z',
            end_at: null,
            is_all_day: false,
            location: null,
            calendar_name: 'Work',
            participants: [],
          },
        },
      ],
      metadata: {query_path: 'deterministic', latency_ms: 10, is_partial: false, cache_hint: null},
    },
    isLoading: false,
    isStale: false,
    error: null,
    refresh: jest.fn(),
  }),
}));

// Mock ConnectivityBanner
jest.mock('../components/ConnectivityBanner', () => ({
  ConnectivityBanner: () => null,
}));

describe('TodayScreen', () => {
  it('renders cards from the query', () => {
    render(<TodayScreen />);
    expect(screen.getByTestID('event-card')).toBeTruthy();
  });

  it('renders without crashing when data is empty', () => {
    const {useTodayQuery} = require('../hooks/useTodayQuery');
    useTodayQuery.mockReturnValueOnce({
      data: {cards: []},
      isLoading: false,
      isStale: false,
      error: null,
      refresh: jest.fn(),
    });

    render(<TodayScreen />);
    expect(screen.getByText('No items today')).toBeTruthy();
  });
});
