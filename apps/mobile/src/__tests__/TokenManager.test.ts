import {TokenManager} from '../services/TokenManager';
import {__clearStore, __setBiometryType} from '../__mocks__/react-native-keychain';
import * as Keychain from 'react-native-keychain';

beforeEach(() => {
  __clearStore();
  __setBiometryType('FaceID');
  TokenManager.setAccessToken(null);
});

describe('TokenManager', () => {
  // ── Access token (in-memory) ──

  it('stores and retrieves access token in memory', () => {
    expect(TokenManager.getAccessToken()).toBeNull();
    TokenManager.setAccessToken('abc123');
    expect(TokenManager.getAccessToken()).toBe('abc123');
  });

  it('clears access token', () => {
    TokenManager.setAccessToken('abc123');
    TokenManager.setAccessToken(null);
    expect(TokenManager.getAccessToken()).toBeNull();
  });

  // ── Token pair ──

  it('setTokens stores access in memory and refresh in Keychain', async () => {
    await TokenManager.setTokens('access-tok', 'refresh-tok');

    expect(TokenManager.getAccessToken()).toBe('access-tok');
    expect(Keychain.setGenericPassword).toHaveBeenCalledWith(
      'user',
      'refresh-tok',
      expect.objectContaining({
        service: 'EkamCore-Mobile-RefreshToken',
        accessControl: 'BiometryAnyOrDevicePasscode',
      }),
    );
  });

  it('getRefreshToken retrieves from Keychain', async () => {
    await TokenManager.setTokens('a', 'my-refresh');
    const refresh = await TokenManager.getRefreshToken();
    expect(refresh).toBe('my-refresh');
  });

  it('getRefreshToken returns null when no token stored', async () => {
    const refresh = await TokenManager.getRefreshToken();
    expect(refresh).toBeNull();
  });

  // ── Clear ──

  it('clearTokens wipes both access and refresh', async () => {
    await TokenManager.setTokens('a', 'r');
    await TokenManager.clearTokens();

    expect(TokenManager.getAccessToken()).toBeNull();
    expect(Keychain.resetGenericPassword).toHaveBeenCalledWith(
      expect.objectContaining({service: 'EkamCore-Mobile-RefreshToken'}),
    );
  });

  // ── hasStoredRefresh ──

  it('hasStoredRefresh returns true when refresh token exists', async () => {
    await TokenManager.setTokens('a', 'r');
    const has = await TokenManager.hasStoredRefresh();
    expect(has).toBe(true);
  });

  it('hasStoredRefresh returns false when no refresh token', async () => {
    const has = await TokenManager.hasStoredRefresh();
    expect(has).toBe(false);
  });

  // ── Biometric ──

  it('getBiometricType returns FaceID when available', async () => {
    __setBiometryType('FaceID');
    const type = await TokenManager.getBiometricType();
    expect(type).toBe('FaceID');
  });

  it('getBiometricType returns TouchID', async () => {
    __setBiometryType('TouchID');
    const type = await TokenManager.getBiometricType();
    expect(type).toBe('TouchID');
  });

  it('getBiometricType returns null when unavailable', async () => {
    __setBiometryType(null);
    const type = await TokenManager.getBiometricType();
    expect(type).toBeNull();
  });

  // ── Backward compat aliases ──

  it('saveRefreshToken and loadRefreshToken work', async () => {
    await TokenManager.saveRefreshToken('compat-token');
    const loaded = await TokenManager.loadRefreshToken();
    expect(loaded).toBe('compat-token');
  });

  it('clearRefreshToken clears via clearTokens', async () => {
    await TokenManager.setTokens('a', 'r');
    await TokenManager.clearRefreshToken();
    expect(TokenManager.getAccessToken()).toBeNull();
  });

  // ── Cert pinning storage ──

  it('stores and loads pinned cert', async () => {
    await TokenManager.storePinnedCert('-----BEGIN CERTIFICATE-----\nABC\n-----END CERTIFICATE-----');
    const cert = await TokenManager.loadPinnedCert();
    expect(cert).toContain('BEGIN CERTIFICATE');
  });

  it('clearPinnedCert removes stored cert', async () => {
    await TokenManager.storePinnedCert('CERT');
    await TokenManager.clearPinnedCert();
    const cert = await TokenManager.loadPinnedCert();
    expect(cert).toBeNull();
  });
});
