/**
 * TokenManager — Keychain-backed token storage with biometric protection (S16-002).
 *
 * Access token: in-memory ONLY (never persisted — TechSpec §19, AD-30).
 * Refresh token: stored in iOS/Android Keychain with biometric gate.
 *
 * Biometric access control:
 *   BIOMETRY_ANY_OR_DEVICE_PASSCODE — Face ID, Touch ID, or device passcode.
 *   WHEN_UNLOCKED_THIS_DEVICE_ONLY — not available in iCloud Keychain backup.
 */

import * as Keychain from 'react-native-keychain';

const REFRESH_SERVICE = 'EkamCore-Mobile-RefreshToken';
const CERT_SERVICE = 'EkamCore-Mobile-PinnedCert';

export type BiometricType = 'FaceID' | 'TouchID' | 'Fingerprint' | 'Iris';

class TokenManagerClass {
  private accessToken: string | null = null;

  // ── Access token (in-memory only) ─────────────────────────────────────

  getAccessToken(): string | null {
    return this.accessToken;
  }

  setAccessToken(token: string | null): void {
    this.accessToken = token;
  }

  // ── Token pair management ─────────────────────────────────────────────

  /**
   * Store both tokens. Access stays in memory; refresh goes to Keychain
   * with biometric protection.
   */
  async setTokens(access: string, refresh: string): Promise<void> {
    this.accessToken = access;
    await Keychain.setGenericPassword('user', refresh, {
      service: REFRESH_SERVICE,
      accessControl:
        Keychain.ACCESS_CONTROL.BIOMETRY_ANY_OR_DEVICE_PASSCODE,
      accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  }

  /**
   * Retrieve refresh token from Keychain.
   * Triggers biometric prompt if the device requires it.
   */
  async getRefreshToken(): Promise<string | null> {
    try {
      const result = await Keychain.getGenericPassword({
        service: REFRESH_SERVICE,
        authenticationPrompt: {
          title: 'Unlock EkamCore',
          subtitle: 'Authenticate to access your data',
          cancel: 'Cancel',
        },
      });
      if (!result) return null;
      return result.password;
    } catch {
      // User cancelled biometric or Keychain error
      return null;
    }
  }

  /**
   * Load refresh token for silent refresh (backward compat alias).
   */
  async loadRefreshToken(): Promise<string | null> {
    return this.getRefreshToken();
  }

  /**
   * Store refresh token (backward compat alias used by old AuthContext).
   */
  async saveRefreshToken(token: string): Promise<void> {
    await Keychain.setGenericPassword('user', token, {
      service: REFRESH_SERVICE,
      accessControl:
        Keychain.ACCESS_CONTROL.BIOMETRY_ANY_OR_DEVICE_PASSCODE,
      accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  }

  /**
   * Clear all tokens. Called on logout.
   */
  async clearTokens(): Promise<void> {
    this.accessToken = null;
    await Keychain.resetGenericPassword({service: REFRESH_SERVICE});
  }

  /** Backward compat alias. */
  async clearRefreshToken(): Promise<void> {
    await this.clearTokens();
  }

  // ── Biometric queries (no prompt triggered) ───────────────────────────

  /**
   * Check if a refresh token is stored without triggering biometric.
   * Used for UI: show "Use Face ID" button if true.
   */
  async hasStoredRefresh(): Promise<boolean> {
    try {
      // On iOS, getInternetCredentials with no auth prompt can check existence.
      // For generic passwords, we check if the service entry exists.
      // getGenericPassword with no authenticationPrompt skips biometric on
      // items that don't require it; for biometric-protected items it will
      // throw or return false without prompting on some RN Keychain versions.
      // Safest approach: try getAllGenericPasswordServices.
      const services =
        await Keychain.getAllGenericPasswordServices();
      return services.includes(REFRESH_SERVICE);
    } catch {
      // Fallback: assume no stored token
      return false;
    }
  }

  /**
   * Check which biometric type is available on this device.
   * Returns null if no biometric hardware or not enrolled.
   */
  async getBiometricType(): Promise<BiometricType | null> {
    try {
      const type = await Keychain.getSupportedBiometryType();
      if (!type) return null;
      switch (type) {
        case Keychain.BIOMETRY_TYPE.FACE_ID:
          return 'FaceID';
        case Keychain.BIOMETRY_TYPE.TOUCH_ID:
          return 'TouchID';
        case Keychain.BIOMETRY_TYPE.FINGERPRINT:
          return 'Fingerprint';
        case Keychain.BIOMETRY_TYPE.IRIS:
          return 'Iris';
        default:
          return null;
      }
    } catch {
      return null;
    }
  }

  // ── TLS cert pinning storage ──────────────────────────────────────────

  async storePinnedCert(certPem: string): Promise<void> {
    await Keychain.setGenericPassword('cert', certPem, {
      service: CERT_SERVICE,
      accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  }

  async loadPinnedCert(): Promise<string | null> {
    try {
      const result = await Keychain.getGenericPassword({
        service: CERT_SERVICE,
      });
      return result ? result.password : null;
    } catch {
      return null;
    }
  }

  async clearPinnedCert(): Promise<void> {
    await Keychain.resetGenericPassword({service: CERT_SERVICE});
  }
}

export const TokenManager = new TokenManagerClass();
