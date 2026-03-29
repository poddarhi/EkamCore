import React from 'react';
import {render, screen, act} from '@testing-library/react-native';
import {Text} from 'react-native';
import {ConnectivityProvider, useConnectivity} from '../contexts/ConnectivityContext';
import {ConnectivityManager} from '../services/ConnectivityManager';

jest.mock('../services/ConnectivityManager', () => {
  const listeners: Set<(s: string) => void> = new Set();
  return {
    ConnectivityManager: {
      start: jest.fn(),
      stop: jest.fn(),
      getState: jest.fn(() => 'CONNECTED'),
      subscribe: jest.fn((cb: (s: string) => void) => {
        listeners.add(cb);
        return () => listeners.delete(cb);
      }),
      __emit: (state: string) => listeners.forEach(l => l(state)),
    },
  };
});

function TestConsumer() {
  const {state, isOnline} = useConnectivity();
  return <Text testID="out">{`${state}:${isOnline}`}</Text>;
}

describe('ConnectivityContext', () => {
  it('starts with CONNECTED state', () => {
    render(
      <ConnectivityProvider>
        <TestConsumer />
      </ConnectivityProvider>,
    );
    expect(screen.getByTestId('out').props.children).toBe('CONNECTED:true');
  });

  it('starts and stops ConnectivityManager on mount/unmount', () => {
    const {unmount} = render(
      <ConnectivityProvider>
        <TestConsumer />
      </ConnectivityProvider>,
    );
    expect(ConnectivityManager.start).toHaveBeenCalled();
    unmount();
    expect(ConnectivityManager.stop).toHaveBeenCalled();
  });

  it('updates state when manager emits DEGRADED', () => {
    render(
      <ConnectivityProvider>
        <TestConsumer />
      </ConnectivityProvider>,
    );

    act(() => {
      (ConnectivityManager as unknown as {__emit: (s: string) => void}).__emit(
        'DEGRADED',
      );
    });

    // DEGRADED is still "online"
    expect(screen.getByTestId('out').props.children).toBe('DEGRADED:true');
  });

  it('marks isOnline false when DISCONNECTED_EMPTY', () => {
    render(
      <ConnectivityProvider>
        <TestConsumer />
      </ConnectivityProvider>,
    );

    act(() => {
      (ConnectivityManager as unknown as {__emit: (s: string) => void}).__emit(
        'DISCONNECTED_EMPTY',
      );
    });

    expect(screen.getByTestId('out').props.children).toBe(
      'DISCONNECTED_EMPTY:false',
    );
  });
});
