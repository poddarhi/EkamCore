/**
 * CertPinningService — TLS certificate pinning for Caddy CA (S16-002).
 *
 * Per TechSpec §17.2:
 * - On first setup, fetches Caddy root CA from hub (/api/v1/system/ca-certificate)
 * - Stores cert PEM in Keychain via TokenManager
 * - Validates server cert against pinned CA on subsequent connections
 * - Shows security warning if cert changes (no silent downgrade)
 *
 * Note: Full SSL pinning in React Native requires native module integration
 * (react-native-ssl-pinning or custom TrustManager). This service manages
 * the cert storage and validation logic; native integration is platform-specific.
 */

import {TokenManager} from './TokenManager';
import {apiClient} from '../api/ApiClient';

export type CertPinningState =
  | 'NOT_PINNED'       // No cert stored yet (first run)
  | 'PINNED'           // Cert stored and matches
  | 'MISMATCH'         // Cert changed — security warning
  | 'FETCH_FAILED';    // Could not fetch cert from hub

class CertPinningServiceClass {
  private state: CertPinningState = 'NOT_PINNED';
  private pinnedCert: string | null = null;

  getState(): CertPinningState {
    return this.state;
  }

  /**
   * Initialize: load pinned cert from Keychain if it exists.
   */
  async init(): Promise<void> {
    this.pinnedCert = await TokenManager.loadPinnedCert();
    this.state = this.pinnedCert ? 'PINNED' : 'NOT_PINNED';
  }

  /**
   * Fetch the Caddy root CA certificate from the hub and pin it.
   * Called during initial setup or when user explicitly re-pins.
   *
   * The API endpoint GET /api/v1/system/ca-certificate returns the
   * Caddy auto-generated root CA in PEM format. This endpoint requires
   * auth (only the authenticated user can read the CA cert).
   */
  async fetchAndPin(): Promise<CertPinningState> {
    try {
      const data = await apiClient.request<{certificate: string}>({
        path: '/system/ca-certificate',
        noRetry: true,
      });

      if (!data.certificate || !data.certificate.includes('BEGIN CERTIFICATE')) {
        this.state = 'FETCH_FAILED';
        return this.state;
      }

      await TokenManager.storePinnedCert(data.certificate);
      this.pinnedCert = data.certificate;
      this.state = 'PINNED';
      return this.state;
    } catch {
      this.state = 'FETCH_FAILED';
      return this.state;
    }
  }

  /**
   * Verify a server certificate against the pinned CA.
   *
   * In a full implementation, this would be called from a native SSL
   * TrustManager/NSURLSessionDelegate. For now, it provides the comparison
   * logic that the native layer can invoke.
   *
   * @param serverCertPem The server's certificate in PEM format
   * @returns true if the cert matches the pinned CA, false otherwise
   */
  verifyCert(serverCertPem: string): boolean {
    if (!this.pinnedCert) {
      // No pinned cert — first connection, allow but warn
      return true;
    }

    // Compare normalized PEM content (strip whitespace differences)
    const normalize = (pem: string) =>
      pem
        .replace(/-----BEGIN CERTIFICATE-----/g, '')
        .replace(/-----END CERTIFICATE-----/g, '')
        .replace(/\s/g, '');

    const pinned = normalize(this.pinnedCert);
    const server = normalize(serverCertPem);

    if (pinned === server) {
      return true;
    }

    // Mismatch — possible MITM
    this.state = 'MISMATCH';
    return false;
  }

  /**
   * Clear the pinned cert (on logout or explicit user action).
   */
  async clearPin(): Promise<void> {
    await TokenManager.clearPinnedCert();
    this.pinnedCert = null;
    this.state = 'NOT_PINNED';
  }

  /**
   * Get a user-facing security warning message when cert mismatches.
   */
  getSecurityWarning(): string {
    return (
      "The hub's TLS certificate has changed. This could indicate a " +
      'security issue. Do not log in until you verify the change is expected ' +
      '(e.g., after re-installing EkamCore on your Mac).'
    );
  }
}

export const CertPinningService = new CertPinningServiceClass();
