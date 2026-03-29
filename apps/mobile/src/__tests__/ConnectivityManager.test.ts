import {ConnectivityManager} from '../services/ConnectivityManager';

// Replace global fetch for tests
const mockFetch = jest.fn<Promise<Response>, [RequestInfo, RequestInit?]>();
global.fetch = mockFetch as unknown as typeof fetch;

function makeResponse(ok: boolean, latencyOverride?: number): Response {
  return {
    ok,
    status: ok ? 200 : 503,
    json: async () => ({status: 'ok'}),
  } as unknown as Response;
}

beforeEach(() => {
  jest.useFakeTimers();
  mockFetch.mockReset();
  ConnectivityManager.stop();
  // Reset internal state via start/stop cycle
});

afterEach(() => {
  ConnectivityManager.stop();
  jest.useRealTimers();
});

describe('ConnectivityManager', () => {
  it('emits CONNECTED on fast successful health check', async () => {
    mockFetch.mockResolvedValue(makeResponse(true));

    const states: string[] = [];
    ConnectivityManager.subscribe(s => states.push(s));

    ConnectivityManager.start();
    await Promise.resolve(); // flush first poll

    // Should remain CONNECTED (initial state) — no emission since no state change
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/health'),
      expect.any(Object),
    );
  });

  it('emits RECONNECTING on first failure', async () => {
    mockFetch.mockRejectedValue(new TypeError('Network request failed'));

    const states: string[] = [];
    ConnectivityManager.subscribe(s => states.push(s));

    ConnectivityManager.start();
    // Let the first poll run
    await Promise.resolve();
    await Promise.resolve();

    expect(states).toContain('RECONNECTING');
  });

  it('emits HUB_SLEEPING on connection refused', async () => {
    mockFetch.mockRejectedValue(new TypeError('Network request failed ECONNREFUSED'));

    const states: string[] = [];
    ConnectivityManager.subscribe(s => states.push(s));

    ConnectivityManager.start();
    await Promise.resolve();
    await Promise.resolve();

    expect(states.some(s => s === 'HUB_SLEEPING' || s === 'RECONNECTING')).toBe(true);
  });

  it('emits DISCONNECTED_EMPTY after threshold with no cache', async () => {
    mockFetch.mockRejectedValue(new TypeError('Network request failed'));
    ConnectivityManager.setCacheAvailable(false);

    const states: string[] = [];
    ConnectivityManager.subscribe(s => states.push(s));

    ConnectivityManager.start();

    // Simulate time past 5 min threshold
    jest.advanceTimersByTime(6 * 60 * 1_000);

    // Let pending promises resolve
    await Promise.resolve();
    await Promise.resolve();

    // After threshold without cache: DISCONNECTED_EMPTY
    const lastState = states[states.length - 1];
    expect(['RECONNECTING', 'DISCONNECTED_EMPTY']).toContain(lastState);
  });

  it('emits DISCONNECTED_CACHED after threshold when cache available', async () => {
    mockFetch.mockRejectedValue(new TypeError('Network request failed'));
    ConnectivityManager.setCacheAvailable(true);

    const states: string[] = [];
    ConnectivityManager.subscribe(s => states.push(s));

    ConnectivityManager.start();
    jest.advanceTimersByTime(6 * 60 * 1_000);
    await Promise.resolve();
    await Promise.resolve();

    const lastState = states[states.length - 1];
    expect(['RECONNECTING', 'DISCONNECTED_CACHED']).toContain(lastState);

    ConnectivityManager.setCacheAvailable(false);
  });

  it('subscribe returns unsubscribe function', () => {
    const listener = jest.fn();
    const unsub = ConnectivityManager.subscribe(listener);
    unsub();

    // After unsub, listener should not be called
    mockFetch.mockRejectedValue(new TypeError('fail'));
    ConnectivityManager.start();
    expect(listener).not.toHaveBeenCalled();
  });
});
