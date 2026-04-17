import {AuthService} from '../services/AuthService';
import {TokenManager} from '../services/TokenManager';
import {apiClient} from '../api/ApiClient';
import {__clearStore} from '../__mocks__/react-native-keychain';

// Mock fetch for ApiClient
const mockFetch = jest.fn<Promise<Response>, [RequestInfo, RequestInit?]>();
(globalThis as Record<string, unknown>).fetch = mockFetch;

// Mock ConnectivityManager
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

// JWT helper: create a minimal valid JWT (manual base64 for Node/Hermes compat)
function toBase64(str: string): string {
  // Manual base64 — avoids Buffer/btoa type issues in RN test env
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let result = '';
  const bytes = Array.from(str).map(c => c.charCodeAt(0));
  for (let i = 0; i < bytes.length; i += 3) {
    const b0 = bytes[i], b1 = bytes[i + 1] ?? 0, b2 = bytes[i + 2] ?? 0;
    result += chars[b0 >> 2] + chars[((b0 & 3) << 4) | (b1 >> 4)];
    result += i + 1 < bytes.length ? chars[((b1 & 15) << 2) | (b2 >> 6)] : '=';
    result += i + 2 < bytes.length ? chars[b2 & 63] : '=';
  }
  return result;
}

function makeJwt(payload: Record<string, unknown>): string {
  const header = toBase64(JSON.stringify({alg: 'RS256', typ: 'JWT'}));
  const body = toBase64(JSON.stringify(payload));
  return `${header}.${body}.fake-signature`;
}

beforeEach(() => {
  mockFetch.mockReset();
  __clearStore();
  TokenManager.setAccessToken(null);
  apiClient.clearAuth();
  apiClient.setBaseUrl('https://test.local/api/v1');
});

describe('AuthService', () => {
  describe('login', () => {
    it('stores tokens and returns user on success', async () => {
      const jwt = makeJwt({sub: 'user-1', role: 'admin', workspaces: ['ws-1']});
      mockFetch.mockResolvedValue(
        jsonResponse({access_token: jwt, refresh_token: 'ref-tok'}),
      );

      const result = await AuthService.login('user@test.com', 'password');

      expect(result.user.id).toBe('user-1');
      expect(result.user.role).toBe('admin');
      expect(TokenManager.getAccessToken()).toBe(jwt);
    });

    it('throws on invalid credentials', async () => {
      mockFetch.mockResolvedValue(
        jsonResponse({error_code: 'AUTH_INVALID_CREDENTIALS', message: 'Bad'}, 401),
      );

      await expect(
        AuthService.login('bad@test.com', 'wrong'),
      ).rejects.toThrow();
    });
  });

  describe('refresh', () => {
    it('returns user when refresh succeeds', async () => {
      // Store a refresh token first
      await TokenManager.saveRefreshToken('stored-refresh');

      const newJwt = makeJwt({sub: 'user-2', role: 'standard', workspaces: ['ws-2']});
      mockFetch.mockResolvedValue(jsonResponse({access_token: newJwt}));

      const user = await AuthService.refresh();

      expect(user).not.toBeNull();
      expect(user!.id).toBe('user-2');
      expect(TokenManager.getAccessToken()).toBe(newJwt);
    });

    it('returns null when no stored refresh token', async () => {
      const user = await AuthService.refresh();
      expect(user).toBeNull();
    });

    it('clears tokens on refresh failure', async () => {
      await TokenManager.saveRefreshToken('old-refresh');
      TokenManager.setAccessToken('old-access');

      mockFetch.mockResolvedValue(
        jsonResponse({error_code: 'AUTH_TOKEN_EXPIRED'}, 401),
      );

      const user = await AuthService.refresh();

      expect(user).toBeNull();
      expect(TokenManager.getAccessToken()).toBeNull();
    });
  });

  describe('unlockWithBiometric', () => {
    it('returns user when biometric + refresh succeeds', async () => {
      await TokenManager.saveRefreshToken('bio-refresh');

      const jwt = makeJwt({sub: 'user-3', role: 'admin', workspaces: []});
      mockFetch.mockResolvedValue(jsonResponse({access_token: jwt}));

      const user = await AuthService.unlockWithBiometric();

      expect(user).not.toBeNull();
      expect(user!.id).toBe('user-3');
    });

    it('returns null when no stored refresh', async () => {
      const user = await AuthService.unlockWithBiometric();
      expect(user).toBeNull();
    });
  });

  describe('logout', () => {
    it('clears all tokens', async () => {
      await TokenManager.setTokens('access', 'refresh');

      // Logout API call (best-effort, may fail)
      mockFetch
        .mockResolvedValueOnce(jsonResponse({csrf_token: 'x'})) // CSRF
        .mockResolvedValueOnce(jsonResponse(null, 204)); // logout

      await AuthService.logout();

      expect(TokenManager.getAccessToken()).toBeNull();
    });

    it('clears tokens even when API call fails', async () => {
      await TokenManager.setTokens('access', 'refresh');
      mockFetch.mockRejectedValue(new TypeError('Network request failed'));

      await AuthService.logout();

      expect(TokenManager.getAccessToken()).toBeNull();
    });
  });

  describe('needsRefresh', () => {
    it('returns true when no token', () => {
      expect(AuthService.needsRefresh()).toBe(true);
    });

    it('returns true when token is expired', () => {
      const expired = makeJwt({sub: 'u', exp: Math.floor(Date.now() / 1000) - 100});
      TokenManager.setAccessToken(expired);
      expect(AuthService.needsRefresh()).toBe(true);
    });

    it('returns false when token is fresh', () => {
      const fresh = makeJwt({sub: 'u', exp: Math.floor(Date.now() / 1000) + 3600});
      TokenManager.setAccessToken(fresh);
      expect(AuthService.needsRefresh()).toBe(false);
    });
  });

  describe('getCurrentUser', () => {
    it('returns user from access token', () => {
      const jwt = makeJwt({sub: 'u-1', role: 'admin', workspaces: ['w']});
      TokenManager.setAccessToken(jwt);
      const user = AuthService.getCurrentUser();
      expect(user?.id).toBe('u-1');
    });

    it('returns null when no token', () => {
      expect(AuthService.getCurrentUser()).toBeNull();
    });
  });
});
