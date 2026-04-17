import {apiClient, ApiError} from '../api/ApiClient';

// ── Mock fetch ──
const mockFetch = jest.fn<Promise<Response>, [RequestInfo, RequestInit?]>();
(globalThis as Record<string, unknown>).fetch = mockFetch;

// ── Mock TokenManager ──
jest.mock('../services/TokenManager', () => ({
  TokenManager: {
    loadRefreshToken: jest.fn().mockResolvedValue(null),
    saveRefreshToken: jest.fn().mockResolvedValue(undefined),
    clearRefreshToken: jest.fn().mockResolvedValue(undefined),
  },
}));

// ── Mock ConnectivityManager ──
jest.mock('../services/ConnectivityManager', () => ({
  ConnectivityManager: {
    getState: jest.fn().mockReturnValue('CONNECTED'),
    start: jest.fn(),
    stop: jest.fn(),
    subscribe: jest.fn().mockReturnValue(() => {}),
    setCacheAvailable: jest.fn(),
  },
}));

function jsonResponse(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
    headers: new Headers(),
  } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
  apiClient.setBaseUrl('https://test.local/api/v1');
  apiClient.setAuthToken('test-access-token');
});

describe('ApiClient', () => {
  // ── Base URL ──

  it('uses configured base URL', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ok: true}));

    await apiClient.request({path: '/today'});

    expect(mockFetch).toHaveBeenCalledWith(
      'https://test.local/api/v1/today',
      expect.any(Object),
    );
  });

  it('uses full URL when path starts with http', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ok: true}));

    await apiClient.request({path: 'https://other.host/health'});

    expect(mockFetch).toHaveBeenCalledWith(
      'https://other.host/health',
      expect.any(Object),
    );
  });

  // ── Auth header ──

  it('injects Authorization header', async () => {
    mockFetch.mockResolvedValue(jsonResponse({data: 'ok'}));

    await apiClient.request({path: '/today'});

    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    expect((callArgs.headers as Record<string, string>)['Authorization']).toBe(
      'Bearer test-access-token',
    );
  });

  it('omits auth header when token is null', async () => {
    apiClient.setAuthToken(null);
    mockFetch.mockResolvedValue(jsonResponse({data: 'ok'}));

    await apiClient.request({path: '/health', noRetry: true});

    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    expect((callArgs.headers as Record<string, string>)['Authorization']).toBeUndefined();
  });

  // ── Retry with backoff ──

  it('retries on network error with backoff', async () => {
    jest.useFakeTimers();

    mockFetch
      .mockRejectedValueOnce(new TypeError('Network request failed'))
      .mockRejectedValueOnce(new TypeError('Network request failed'))
      .mockResolvedValueOnce(jsonResponse({ok: true}));

    const promise = apiClient.request({path: '/today'});

    // Advance past first retry delay (500ms)
    jest.advanceTimersByTime(600);
    await Promise.resolve();

    // Advance past second retry delay (1000ms)
    jest.advanceTimersByTime(1100);
    await Promise.resolve();

    const result = await promise;
    expect(result).toEqual({ok: true});
    expect(mockFetch).toHaveBeenCalledTimes(3);

    jest.useRealTimers();
  });

  it('does not retry on 4xx errors', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({error_code: 'VALIDATION_ERROR', message: 'Bad input'}, 422),
    );

    await expect(apiClient.request({path: '/today'})).rejects.toThrow(ApiError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('does not retry when noRetry is set', async () => {
    mockFetch.mockRejectedValue(new TypeError('Network request failed'));

    await expect(
      apiClient.request({path: '/today', noRetry: true}),
    ).rejects.toThrow();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  // ── 401 refresh flow ──

  it('attempts refresh on 401 then retries', async () => {
    const {TokenManager} = require('../services/TokenManager');
    TokenManager.loadRefreshToken.mockResolvedValue('stored-refresh-token');

    // First call: 401
    // CSRF fetch: 404 (no CSRF endpoint)
    // Refresh call: success with new token
    // Retry: success
    mockFetch
      .mockResolvedValueOnce(jsonResponse({error_code: 'AUTH_TOKEN_EXPIRED'}, 401)) // original
      .mockResolvedValueOnce(jsonResponse({access_token: 'new-token'}, 200)) // refresh
      .mockResolvedValueOnce(jsonResponse({data: 'after-refresh'})); // retry

    const result = await apiClient.request({path: '/today', noRetry: true});
    expect(result).toEqual({data: 'after-refresh'});

    // Verify refresh was called
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  // ── CSRF for mutations ──

  it('fetches CSRF token for POST requests', async () => {
    // First call: CSRF fetch
    // Second call: actual POST
    mockFetch
      .mockResolvedValueOnce(jsonResponse({csrf_token: 'csrf-123'})) // CSRF
      .mockResolvedValueOnce(jsonResponse({id: 'new-item'})); // POST

    await apiClient.request({
      path: '/reminders',
      method: 'POST',
      body: {title: 'test'},
      noRetry: true,
    });

    // Verify CSRF header was sent on the POST
    const postCall = mockFetch.mock.calls[1][1] as RequestInit;
    expect((postCall.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-123');
  });

  // ── Error parsing ──

  it('parses API error body into ApiError', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {error_code: 'NOT_FOUND', message: 'Resource not found', correlation_id: 'abc-123'},
        404,
      ),
    );

    try {
      await apiClient.request({path: '/missing', noRetry: true});
      fail('Should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.errorCode).toBe('NOT_FOUND');
      expect(apiErr.correlationId).toBe('abc-123');
    }
  });

  // ── 204 No Content ──

  it('returns undefined for 204 responses', async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse({csrf_token: 'x'})) // CSRF
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: async () => undefined,
        headers: new Headers(),
      } as unknown as Response);

    const result = await apiClient.request({
      path: '/resource',
      method: 'DELETE',
      noRetry: true,
    });
    expect(result).toBeUndefined();
  });

  // ── clearAuth ──

  it('clearAuth resets token and CSRF', () => {
    apiClient.setAuthToken('token');
    apiClient.clearAuth();
    expect(apiClient.getAuthToken()).toBeNull();
  });
});
