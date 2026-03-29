/**
 * Secure token storage using react-native-keychain.
 *
 * Refresh token is stored in the system keychain under a fixed service name.
 * Access token is never persisted — it lives in memory only (api/client.ts).
 */
import * as Keychain from 'react-native-keychain';

const SERVICE = 'ekamcore.refresh_token';

export const TokenManager = {
  async saveRefreshToken(token: string): Promise<void> {
    await Keychain.setGenericPassword('refresh', token, {service: SERVICE});
  },

  async loadRefreshToken(): Promise<string | null> {
    const result = await Keychain.getGenericPassword({service: SERVICE});
    if (!result) return null;
    return result.password;
  },

  async clearRefreshToken(): Promise<void> {
    await Keychain.resetGenericPassword({service: SERVICE});
  },
};
